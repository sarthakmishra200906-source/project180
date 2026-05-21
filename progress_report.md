# Project 180 — Progress Report

Date: 2026-05-19

Summary
-------
This report documents work completed for Project 180 up to 2026-05-19. The goal was to scaffold a mobile-friendly chat UI and an AI orchestration backend with cloud-first (Gemini) and local-first (Ollama) failover, plus developer tooling for testing and log capture.

What I implemented
------------------
- Project scaffold with `server/` including Flask app and core modules.
- `.env` support via `python-dotenv` in `server/config.py` (loadable `GEMINI_API_KEY`, `OLLAMA_MODEL`, `SERVER_HOST`, `SERVER_PORT`).
- AI orchestration in `server/core/ai_brain.py`:
  - Cloud-first attempts (attempts to use `google.generativeai` if `GEMINI_API_KEY` is set).
  - Robust Ollama local fallback: streaming NDJSON parsing via `requests.post(..., stream=True)` and `iter_lines()`.
  - NDJSON and raw-text assembly into a single clean response string.
  - Response cleaning to remove trailing model tokens and safety/refusal detection.
  - Language-aware fallbacks: Hindi/Hinglish canned replies when requested and model output lacks Devanagari.
- Flask server in `server/app.py`:
  - Mobile-friendly chat UI at `/` with single-line input and `Send` button.
  - Client-side streaming: `sendPrompt()` creates one AI bubble and fills it incrementally with NDJSON or plain text from `/ai`.
  - Endpoints: `/ai` (POST) returns `text/plain` responses, `/client_log` (POST) persists client logs to `logs/client.log`.
  - Diagnostic prints for backend prompt receipt.
- Tests and utilities:
  - `server/test_ai.py` and `server/test_language_fallback.py` used during development.
  - PowerShell helper snippets and instructions to run server and test from phone.
- Dev ergonomics:
  - Client logs appended to `logs/client.log` and a tail command demonstrated for live debugging.
  - Scripts to move project or Ollama storage (created earlier) available but not executed.

Files changed (high level)
-------------------------
- `server/app.py` — updated frontend send logic to stream responses; return `text/plain` from `/ai`.
- `server/core/ai_brain.py` — added streaming NDJSON parsing, response cleaning, language-aware fallback, refusal detection.
- `server/test_language_fallback.py` — simple validation helper.
- `progress_report.md` — this file.

Current runtime status
----------------------
- Server was running at `http://192.168.31.100:8787` during tests. I have stopped the running server and associated log tailing processes now as requested.

How to start the server (when you resume)
-----------------------------------------
1. Activate venv and start server:

```powershell
. .venv\Scripts\Activate.ps1
python -m server.app
```

2. Open the chat UI on your phone (same LAN):

- http://<your-laptop-ip>:8787/  (example: http://192.168.31.100:8787/)

3. To tail client logs while testing:

```powershell
Get-Content .\logs\client.log -Wait -Tail 50
```

Notes / Observations
--------------------
- The `google.generativeai` package used in the code is deprecated and emits a FutureWarning; migrating to `google.genai` is recommended for cloud Gemini calls.
- Ollama calls can be slow while models load; NDJSON streaming is handled to provide incremental UI updates.
- The server currently uses Flask dev server — for production use a WSGI server (gunicorn/uvicorn, etc.).

Next recommended steps
----------------------
1. Replace `google.generativeai` with `google.genai` (if Gemini cloud access is desired).
2. Move Ollama model storage to a non-C: drive if disk space or OneDrive interference is a concern.
3. Harden server for production (WSGI, reverse proxy) if exposing beyond dev LAN.
4. Add unit/integration tests for NDJSON parsing and language-fallback behavior.
5. Optionally implement authentication on `/ai` if the server will be exposed outside a private LAN.

If you want me to take any of the next steps before you return (e.g., migrate to `google.genai` or prepare a production Docker/WGSI setup), tell me which and I'll continue.

— Copilot

---

## Update: 2026-05-22 — Work completed today (brief + detailed)

Brief
-----
- Implemented session-based "logic" conversation history so multi-turn Q/A is preserved per client for 1 hour.
- Made the controller send a persistent `clientId` (stored in `localStorage`) with `/ai` requests so the server can associate chat history with a device.
- Added server-side cleanup and small debug endpoints to inspect or clear session history.

Detailed
--------
- Server changes (`server/app.py`):
  - Added an in-memory `LOGIC_SESSIONS` store with thread-safe helpers to append history and build prompts that include recent Q/A. This allows the model to see prior user questions and assistant answers when a session is active.
  - `POST /ai` now accepts `session_id` (or `client_id`) in the JSON body. If present, the server prepends recent history (up to recent items) to the prompt passed to the `AIBrain`, and after the response it appends both the user prompt and assistant answer to the session history.
  - Background cleanup thread (`_cleanup_expired_sessions_loop`) removes sessions that have been inactive for 1 hour (TTL = 3600s).
  - Debug endpoints added: `GET /logic_history` (summary of active sessions) and `POST /logic_history/clear` (clear a session by id).

- Client changes (`web_controller/script.js`):
  - Generates and persists a `project180_client_id` in `localStorage` and includes it as `session_id` in `/ai` requests so the server can map requests to session history.
  - No change to the voice wakeword logic itself — multi-turn behavior now works because the server receives the client id and includes prior Q/A in the prompt.

- Behavior and limitations:
  - History is in-memory only (ephemeral). Restarting the server clears histories. If you want persistence across restarts, we should persist to a small file or lightweight DB (SQLite/LevelDB).
  - The server includes recent history entries (sliced to avoid very long prompts). You can tune how many items to include or summarize history before sending to the model.
  - Self-signed `ssl_context='adhoc'` still requires accepting the certificate on the phone browser; this is unrelated to the session feature.

- How to test quickly:
  1. Start the server on your laptop as normal.
  2. From the phone controller, ensure `project180_client_id` is created (open browser dev tools or check localStorage). You can clear it to force a new id for testing.
  3. Say `logic describe cpu` then `logic what is it used for` — the second question will include the first Q/A in the prompt and should appear more context-aware.
  4. Inspect `GET /logic_history` to see active sessions and `POST /logic_history/clear` with `{"session_id":"<id>"}` to clear a session.

- Next recommended improvements:
  - Persist sessions to disk (SQLite) to survive server restarts if desired.
  - Add a controller UI button to clear the local `clientId` for convenience when testing multiple devices.
  - Add per-session size limits and optional summarization to avoid long prompts on extended multi-turn sessions.

If you'd like, I can add the `Clear clientId` UI button to the controller now, or implement persistent storage for session history — which would you prefer next?
