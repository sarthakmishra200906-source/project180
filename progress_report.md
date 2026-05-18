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
