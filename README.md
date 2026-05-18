# Project 180 — Cheeku Companion Robot

This workspace contains firmware, a local Python server, a web controller, and documentation for the Cheeku companion robot.

Important note about disk space
- Your C: drive may be low on space. It's strongly recommended to move this project to `D:\project_180` (or another large drive) before pulling more models or storing large data.

To move the workspace to D: (recommended):
1. Close any editors.
2. Copy the folder from its current location to `D:\project_180`.
3. Open the new folder in VS Code.

Basic setup

1. Create a Python virtual environment and install server dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r server/requirements.txt
```

2. If you haven't already pulled local Ollama models, use these commands (already done in this workspace):

```bash
ollama pull llama3.2:1b
ollama pull qwen2.5:1.5b
ollama pull gemma:2b
```

3. Add your Gemini API key to the `.env` file at the project root:

```
GEMINI_API_KEY=your_api_key_here
```

Run the server (starts HTTP endpoint at `http://127.0.0.1:8787/ai`):

```bash
python -m server.app
```

Test the AI endpoint with `curl`:

```bash
curl -X POST -H "Content-Type: application/json" -d '{"prompt":"Hello"}' http://127.0.0.1:8787/ai
```

If you need to move Ollama's model storage to D:, check Ollama docs for configuration options or use symbolic links to place model storage on D:.

Quick automated relocation script

If you want to move existing Ollama models off C: and create a junction to D:, run the provided PowerShell script as Administrator:

```powershell
.\move_ollama_storage.ps1
```

This will:
- Stop Ollama processes (best-effort), copy models to `D:\Ollama_Models`, remove the old folder under `%USERPROFILE%\.ollama\models`, and create a directory junction so Ollama continues to find models at the same path.

---
