# Progress Report — Project 180 (Cheeku)

Date: 2026-05-19

## Summary
I wired the AI pipeline, pulled offline models, added an HTTP AI endpoint and a test harness, fixed response parsing issues, and added documentation and scripts to avoid C: drive space problems.

## Today’s controller work
Today I focused on the web controller experience for both mobile and laptop use. The controller is now served from the Flask app, includes a dedicated connect button, supports WebSocket connection feedback, and can send live drive/steer messages from both touch and desktop input.

### Done
- Added a dedicated connection panel to `web_controller/index.html` with ESP32 IP input, connect/disconnect button, status indicator, and payload debug text.
- Implemented the connection handshake in `web_controller/script.js` with a 4.5 second timeout and clear success/failure UI states.
- Added unified `transmitData(header, value)` messaging so steering and drive commands update the on-screen payload and send over WebSocket when connected.
- Implemented mobile steering behavior using wheel drag logic, angle normalization, clamping, and spring-back on release.
- Added desktop keyboard support for `W`, `A`, `S`, `D` and arrow keys.
- Added tap/click handling and visual pressed-state feedback for controller buttons.
- Added mouse drag fallback for the steering wheel so desktop browser steering works even when pointer events are not reliable in the test environment.
- Reduced layout overlap by adjusting the controller stage and switch area spacing in `web_controller/style.css`.
- Kept the controller accessible through the Flask server at `/controller` so phones and laptops can open the same UI over the local network.

### Verified
- The controller page loads from the laptop-hosted Flask server.
- Laptop mode buttons respond and update the payload display.
- Mobile mode steering wheel responds to drag and springs back to center.
- Desktop mouse dragging on the steering wheel now updates the steering payload.
- The connection button changes state correctly and shows failure text when no ESP32 is available.

### Left to do
- Connect the controller to the real ESP32 WebSocket endpoint and confirm the robot receives live `STEER` and `DRIVE` messages on hardware.
- Match the exact ESP32 message protocol if the firmware expects a different format than `HEADER:VALUE`.
- Add on-page connection success/failure styling polish for the status indicator if needed.
- Optional: add hold-to-drive behavior for laptop buttons if you want continuous driving rather than tap-based commands.
- Optional: add a small on-screen troubleshooting note for users who cannot reach the ESP32 from their device.

## What I changed / added (key files)
- `.copilot-context.md` — project overview (initial)
- `firmware/` — placeholder ESP32 and test sketches
- `server/config.py` — now reads `.env` (uses `python-dotenv` when available)
- `.env` — placeholder for `GEMINI_API_KEY`
- `server/requirements.txt` — added `python-dotenv`, `flask`
- `server/core/ai_brain.py` — wired cloud-first Gemini candidate list and local Ollama fallback chain; improved Ollama response parsing
- `server/__init__.py` — package initializer so imports work
- `server/app.py` — simple Flask `/ai` POST endpoint that proxies to `AIBrain.respond()`
- `server/test_ai.py` — test harness that calls `AIBrain.respond()` directly
- `docs/models.md` — Final 5 model list + `ollama pull` commands
- Pulled locally: `llama3.2:1b`, `qwen2.5:1.5b`, `gemma:2b` (confirmed via `ollama list`)
- `README.md` — setup, run, and D: drive guidance
- `docs/progress_report.md` — this file
- `move_to_d.ps1` — convenience script to copy the repo to `D:\project_180`

## AI wiring details
- Cloud candidate models tried in order:
  - `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash-latest`, `gemini-1.5-flash-002`
- Local Ollama fallback list tried in order:
  - `gemma:2b`, `qwen2.5:1.5b`, `llama3.2:1b`
- Behavior: attempt cloud models if `GEMINI_API_KEY` is set and `google.generativeai` is importable; otherwise iterate local Ollama models through `http://localhost:11434/api/generate`.
- Ollama parsing: handle JSON responses and plain text/NDJSON fallbacks.

## Tests performed
- Ran `python server/test_ai.py` with `PYTHONPATH` set to project root.
  - Result: a successful streamed response from `gemma:2b` was returned for the sample prompt.
- Confirmed local models available via `ollama list`.

## How to reproduce locally
1. (Optional) Move project to D: to avoid C: space issues. Use the provided PowerShell script:

```powershell
# Run in PowerShell from project root
.\move_to_d.ps1
```

2. Create venv and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r server/requirements.txt
```

3. Add your Gemini key to `.env` at the project root:

```
GEMINI_API_KEY=your_api_key_here
```

4. Ensure Ollama daemon is running locally (default HTTP API port 11434) and the pulled models are present (`ollama list`).

5. Run the server HTTP AI endpoint:

```bash
python -m server.app
```

6. Test the endpoint:

```bash
curl -X POST -H "Content-Type: application/json" -d '{"prompt":"Hello"}' http://127.0.0.1:8787/ai
```

Or use the provided test harness:

```powershell
$env:PYTHONPATH = "C:\Users\Dell\OneDrive\Desktop\project_180"; python server/test_ai.py
```

## Notes and recommendations
- Disk usage: Ollama models are large. Keep the project on `D:` or configure Ollama's model storage to a large-volume path.
- Running the server + models simultaneously may require >2GB VRAM depending on model combination; `gemma:2b` and `llama3.2:1b` are chosen for small footprints.
- If you want automatic relocation of model storage, we can add scripts to symlink Ollama's model directory to `D:` — I can add that next.

## Next steps I can take for you
- Add a small integration test that starts the Flask app in a subprocess and calls `/ai`.
- Add symlink/script to move Ollama model storage to `D:`.
- Flesh out `server/network_hub.py` to accept socket connections from the ESP32 or mobile remote.

---

Report generated by the project assistant.
