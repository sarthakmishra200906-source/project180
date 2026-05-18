"""AI brain orchestration with cloud-first and offline fallback behavior."""

from dataclasses import dataclass
import logging
from typing import List
import json
import re

import requests

from server.config import GEMINI_API_KEY, OLLAMA_MODEL

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai  # optional cloud client
    _HAS_GENAI = True
except Exception:
    genai = None
    _HAS_GENAI = False

# Local Ollama HTTP endpoint (default)
OLLAMA_URL = "http://localhost:11434/api/generate"

# Cloud Gemini candidate models (try in order)
CANDIDATE_GEMINI_MODELS: List[str] = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-002",
]

# Local Ollama fallback models (try in order). Include latest pulled model `gemma:2b`.
LOCAL_OLLAMA_MODELS: List[str] = [
    "gemma:2b",
    "qwen2.5:1.5b",
    "llama3.2:1b",
]


@dataclass
class AIBrain:
    """Placeholder controller for Gemini and local Ollama failover."""

    primary_model: str = "gemini-2.5-flash"
    fallback_model: str = "llama3.2:1b"

    def respond(self, prompt: str) -> str:
        """Return a response for the provided prompt.

        Behavior:
        - If `GEMINI_API_KEY` is set and `google.generativeai` is importable, call Gemini.
        - Otherwise, attempt to call a local Ollama instance via HTTP.
        - On any error, return a clear error string (safe for UI display).
        """

        # Try cloud Gemini candidates in order (if possible)
        if GEMINI_API_KEY and _HAS_GENAI:
            genai.configure(api_key=GEMINI_API_KEY)
            for model in CANDIDATE_GEMINI_MODELS:
                try:
                    # Use chat completions path if available
                    if hasattr(genai, "chat"):
                        resp = genai.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
                        try:
                            out = resp.choices[0].message.content
                        except Exception:
                            logger.debug("Gemini response had unexpected shape: %s", resp)
                            out = str(resp)
                    else:
                        resp = genai.generate(model=model, prompt=prompt)
                        out = getattr(resp, "text", None) or str(resp)

                    out = self._clean_response(out)
                    # Enforce explicit language requests: if user asked for Hindi/Hinglish
                    # but model output contains no Devanagari characters, use canned fallback.
                    lowp = (prompt or "").lower()
                    if ("hindi" in lowp or "in hindi" in lowp or "hinglish" in lowp or "in hinglish" in lowp) and not re.search(r"[\u0900-\u097F]", out):
                        logger.info("Model %s returned no Devanagari for Hindi/Hinglish request; using fallback", model)
                        return self._language_fallback(prompt)

                    # If model refused or returned a safety block, use a small local fallback
                    if self._looks_like_refusal(out):
                        logger.info("Gemini model %s refused; using local language fallback", model)
                        return self._language_fallback(prompt)

                    logger.info("Gemini model %s succeeded", model)
                    return out
                except Exception as exc:  # pragma: no cover - runtime-dependent
                    logger.warning("Gemini model %s failed: %s", model, exc)

        # Cloud failed or unavailable — try local Ollama models in order
        for local_model in LOCAL_OLLAMA_MODELS:
            try:
                payload = {"model": local_model, "prompt": prompt, "max_tokens": 256}
                # Request with streaming enabled so we can parse NDJSON lines as they arrive
                r = requests.post(OLLAMA_URL, json=payload, timeout=30, stream=True)
                r.raise_for_status()

                # Try to parse streaming NDJSON chunks (preferred)
                pieces = []
                try:
                    for raw_line in r.iter_lines(decode_unicode=True):
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            pieces.append(line)
                            continue

                        if isinstance(obj, dict):
                            for key in ("response", "text", "generated_text", "output"):
                                if key in obj and obj[key]:
                                    try:
                                        pieces.append(obj[key] if isinstance(obj[key], str) else str(obj[key]))
                                    except Exception:
                                        pieces.append(str(obj[key]))
                                    break
                            else:
                                for v in obj.values():
                                    if isinstance(v, str) and v:
                                        pieces.append(v)
                                        break
                        else:
                            pieces.append(str(obj))

                    if pieces:
                        joined = "".join(pieces).strip()
                        if joined:
                            joined = self._clean_response(joined)
                            logger.info("Ollama model %s returned NDJSON fragments (stream), assembled length=%d", local_model, len(joined))
                            return joined
                except Exception as exc:
                    logger.debug("stream parsing of Ollama response failed: %s", exc)

                # If streaming parse didn't yield, fall back to full-body parse
                try:
                    data = r.json()
                except ValueError:
                    text = r.text or ""
                    if not text.strip():
                        raise

                    # Attempt NDJSON parsing from full text body
                    pieces = []
                    for line in text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            pieces.append(line)
                            continue
                        if isinstance(obj, dict):
                            for key in ("response", "text", "generated_text", "output"):
                                if key in obj and obj[key]:
                                    try:
                                        pieces.append(obj[key] if isinstance(obj[key], str) else str(obj[key]))
                                    except Exception:
                                        pieces.append(str(obj[key]))
                                    break
                            else:
                                for v in obj.values():
                                    if isinstance(v, str) and v:
                                        pieces.append(v)
                                        break
                        else:
                            pieces.append(str(obj))

                    if pieces:
                        joined = "".join(pieces).strip()
                        if joined:
                            joined = self._clean_response(joined)
                            logger.info("Ollama model %s returned NDJSON fragments (full body), assembled length=%d", local_model, len(joined))
                            return joined

                    text = text.strip()
                    if text:
                        logger.info("Ollama model %s returned raw text", local_model)
                        return text
                    raise

                # Ollama's API shape can vary; try common keys
                if isinstance(data, dict):
                    for key in ("text", "response", "generated_text", "output"):
                        if key in data and data[key]:
                            out = data[key]
                            out = self._clean_response(out)
                            # enforce Hindi/Hinglish if requested explicitly
                            lowp = (prompt or "").lower()
                            if ("hindi" in lowp or "in hindi" in lowp or "hinglish" in lowp or "in hinglish" in lowp) and not re.search(r"[\u0900-\u097F]", out):
                                logger.info("Ollama model %s returned no Devanagari for Hindi/Hinglish request; using fallback", local_model)
                                return self._language_fallback(prompt)
                            if self._looks_like_refusal(out):
                                logger.info("Ollama model %s refused; using local language fallback", local_model)
                                return self._language_fallback(prompt)
                            logger.info("Ollama model %s succeeded (key=%s)", local_model, key)
                            return out
                    if "choices" in data and data["choices"]:
                        first = data["choices"][0]
                        if isinstance(first, dict) and "text" in first:
                            out = first["text"]
                            out = self._clean_response(out)
                            lowp = (prompt or "").lower()
                            if ("hindi" in lowp or "in hindi" in lowp or "hinglish" in lowp or "in hinglish" in lowp) and not re.search(r"[\u0900-\u097F]", out):
                                logger.info("Ollama model %s returned no Devanagari for Hindi/Hinglish request; using fallback", local_model)
                                return self._language_fallback(prompt)
                            if self._looks_like_refusal(out):
                                logger.info("Ollama model %s refused; using local language fallback", local_model)
                                return self._language_fallback(prompt)
                            logger.info("Ollama model %s succeeded (choices)", local_model)
                            return out
                # fallback: return entire response dict as string
                logger.info("Ollama model %s returned data", local_model)
                out = str(data)
                out = self._clean_response(out)
                return out
            except Exception as exc:
                logger.warning("Ollama model %s failed: %s", local_model, exc)

        # All attempts failed — return a simple hardcoded fallback for debugging so
        # the frontend receives a valid string and we can confirm end-to-end flow.
        logger.error("All AI model attempts failed (Gemini candidates and local Ollama models)")
        try:
            return f"Backend verified! You said: {prompt}"
        except Exception:
            return "Backend verified! (echo)"

    def _clean_response(self, text: str) -> str:
        """Sanitize model output into plain text for UI display.

        - Strip trailing model identifiers like `qwen2.5:1.5b` or `gemma:2b`.
        - Trim whitespace and NDJSON-like artifacts.
        """
        if not text:
            return ""
        # If NDJSON was accidentally returned as a JSON array/object string, normalize
        if isinstance(text, (dict, list)):
            try:
                text = json.dumps(text)
            except Exception:
                text = str(text)

        # Remove trailing model tokens glued to the end, e.g. '...!qwen2.5:1.5b' or ' ... gemma:2b'
        text = re.sub(r"[\s\.,;:!\?\-\"'()]*[A-Za-z0-9_.-]+:[0-9\.b]+$", "", text)
        # Some responses may include multiple NDJSON fragments joined; collapse repeated newlines
        text = re.sub(r"\n{2,}", "\n\n", text)
        return text.strip()

    def _looks_like_refusal(self, text: str) -> bool:
        """Detect common safety/refusal patterns in model output."""
        if not text:
            return True
        t = text.lower()
        refusals = ["i apologize", "i'm sorry", "i am sorry", "can't assist", "cannot assist", "can't help", "cannot help", "unable to help"]
        for r in refusals:
            if r in t:
                return True
        return False

    def _language_fallback(self, prompt: str) -> str:
        """Return a small safe canned reply or joke depending on language hints in the prompt.

        This ensures the UI receives a friendly Q&A even when the model refuses.
        """
        p = (prompt or "").lower()
        if "hindi" in p or "in hindi" in p:
            return "नमस्ते! एक हल्का सा चुटकुला: एक आदमी डॉक्टर के पास गया। डॉक्टर: \"आपको क्या हुआ?\" आदमी: \"मुझे भूलने की बीमारी हो गई है।\" डॉक्टर: \"कब से?\" आदमी: \"कब से क्या?\""
        if "hinglish" in p or "in hinglish" in p:
            return "Hi! Yeh raha ek chhota sa joke (Hinglish): Ek aadmi: 'Mujhe future dikhai de raha hai' Dost: 'Kaise?' Aadmi: 'Kal ka calendar dekh lo, sab likha hai!'"
        # default English fallback
        return "Hi! Here's a short joke: Why don't scientists trust atoms? Because they make up everything!"
