"""Project 180 server: simple HTTP wrapper around the AI brain with a mobile UI."""

from pathlib import Path

from flask import Flask, request, jsonify, render_template, render_template_string, Response, send_from_directory
from flask_socketio import SocketIO, emit
import requests
from server.core.ai_brain import AIBrain
from server.config import SERVER_HOST, SERVER_PORT, ESP32_BASE_URL, DEFAULT_PERSONA
import threading
import time
from datetime import datetime, timedelta


LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
WEB_CONTROLLER_DIR = Path(__file__).resolve().parents[1] / "web_controller"


app = Flask(__name__, template_folder=str(WEB_CONTROLLER_DIR))
socketio = SocketIO(app, cors_allowed_origins="*")
brain = AIBrain()
app.logger.setLevel(10)

# In-memory logic session store: maps session_id -> { history: [{role, text}], last_active: datetime }
LOGIC_SESSIONS = {}
LOGIC_LOCK = threading.Lock()
LOGIC_TTL_SECONDS = 60 * 60  # 1 hour

def _append_to_history(session_id: str, role: str, text: str) -> None:
    if not session_id:
        return
    now = datetime.utcnow()
    with LOGIC_LOCK:
        sess = LOGIC_SESSIONS.get(session_id)
        if not sess:
            sess = {"history": [], "last_active": now}
            LOGIC_SESSIONS[session_id] = sess
        sess["history"].append({"role": role, "text": text})
        sess["last_active"] = now

def _build_prompt_with_history(session_id: str, new_prompt: str) -> str:
    # Prepend recent history as simple Q/A transcript to give the model context.
    if not session_id:
        return new_prompt
    with LOGIC_LOCK:
        sess = LOGIC_SESSIONS.get(session_id)
        if not sess or not sess.get("history"):
            return new_prompt
        parts = []
        # Include up to last 20 items to avoid overly long prompts
        recent = sess["history"][-40:]
        for item in recent:
            role = item.get("role")
            text = item.get("text")
            if role and text:
                if role == "user":
                    parts.append(f"User: {text}")
                else:
                    parts.append(f"Assistant: {text}")
        parts.append(f"User: {new_prompt}")
        return "\n".join(parts)

def _cleanup_expired_sessions_loop():
    while True:
        try:
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=LOGIC_TTL_SECONDS)
            removed = []
            with LOGIC_LOCK:
                for sid, sess in list(LOGIC_SESSIONS.items()):
                    if sess.get("last_active") and sess["last_active"] < cutoff:
                        removed.append(sid)
                        del LOGIC_SESSIONS[sid]
            if removed:
                app.logger.info("Expired logic sessions removed: %s", removed)
        except Exception:
            app.logger.exception('Error during logic session cleanup')
        time.sleep(60)



CHAT_TEMPLATE = """
<!doctype html>
<html lang="en">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Cheeku — Local AI Chat</title>
        <style>
            :root{--bg:#0b0f14;--panel:#0f1720;--muted:#94a3b8;--accent:#7c3aed;--user:#0ea5a4}
            html,body{height:100%;margin:0;background:linear-gradient(180deg,var(--bg),#071018);font-family:Inter,system-ui,Segoe UI,Roboto,Arial}
            .app{max-width:900px;margin:0 auto;height:100vh;display:flex;flex-direction:column}
            header{padding:16px;color:white;display:flex;align-items:center;gap:12px}
            .brand{font-weight:700;font-size:18px}
            main.chat{flex:1;display:flex;flex-direction:column;padding:12px;gap:8px;overflow:hidden}
            .messages{flex:1;overflow:auto;padding:12px;background:linear-gradient(180deg,rgba(255,255,255,0.02),transparent);border-radius:12px}
            .bubble{max-width:78%;padding:10px 14px;margin:8px 0;border-radius:12px;line-height:1.3}
            .ai{background:linear-gradient(180deg,#0b1620,#07101a);color:#e6eef6;border:1px solid rgba(255,255,255,0.02);align-self:flex-start}
            .me{background:linear-gradient(180deg,#043337,#044343);color:white;border:1px solid rgba(255,255,255,0.03);align-self:flex-end}
            footer{padding:10px;display:flex;gap:8px;background:transparent}
            input.chat-input{flex:1;min-height:48px;border-radius:10px;padding:10px;background:#06121a;color:#e6eef6;border:1px solid rgba(255,255,255,0.03)}
            button.send{background:var(--accent);color:white;border:none;padding:10px 14px;border-radius:10px;font-weight:600}
            .muted{color:var(--muted);font-size:13px}
            .loader{font-style:italic;color:var(--muted);margin:6px}
            @media (max-width:600px){.app{padding:0 8px}.brand{font-size:16px}}
        </style>
    </head>
    <body>
        <div class="app">
            <header>
                <div class="brand">Cheeku — Companion AI</div>
                <div style="margin-left:auto" class="muted">Local host: {{ host }}:{{ port }}</div>
            </header>

            <main class="chat">
                <div class="messages" id="messages" aria-live="polite"></div>
                <div class="loader" id="loader" style="display:none">Cheeku is thinking...</div>
            </main>

            <footer>
                <form id="chat-form" style="display:flex;gap:8px;width:100%;">
                    <input id="input" class="chat-input" type="text" placeholder="Say something to Cheeku..." enterkeyhint="send" autocomplete="off" autocapitalize="sentences" spellcheck="true" />
                    <button type="submit" class="send" id="send">Send</button>
                </form>
            </footer>
        </div>

        <script>
            const messages = document.getElementById('messages')
            const chatForm = document.getElementById('chat-form')
            const input = document.getElementById('input')
            const send = document.getElementById('send')
            const loader = document.getElementById('loader')

            function appendBubble(text, who){
                const el = document.createElement('div')
                el.className = 'bubble ' + (who==='me'? 'me' : 'ai')
                el.textContent = text
                messages.appendChild(el)
                messages.scrollTop = messages.scrollHeight
            }

            chatForm.addEventListener('submit', (e) => {
                e.preventDefault()
                sendPrompt()
            })

            async function sendPrompt(){
                const prompt = input.value.trim()
                if(!prompt) return
                // Create user bubble and prepare AI bubble for streamed or single response
                appendBubble(prompt, 'me')
                input.value = ''
                loader.style.display = 'block'
                send.disabled = true
                reportLog('info', 'sendPrompt called with: ' + prompt)

                // Prepare an AI bubble that we'll fill incrementally
                const aiBubble = document.createElement('div')
                aiBubble.className = 'bubble ai'
                aiBubble.textContent = ''
                messages.appendChild(aiBubble)
                messages.scrollTop = messages.scrollHeight

                try{
                    function getPersonaPrefix(){
                        try{
                            const stored = localStorage.getItem('project180_persona');
                            if(stored && stored.trim()) return stored.trim();
                        }catch(_){}
                        return "You are Cheeku, a friendly, concise companion robot. Answer in-character and speak as Cheeku when asked to describe yourself.";
                    }
                    const persona = getPersonaPrefix();
                    const finalPrompt = persona + "\n\n" + prompt;
                    const res = await fetch('/ai', {method:'POST',headers:{'Content-Type':'application/json'},body: JSON.stringify({prompt: finalPrompt})})
                    if(!res.ok){
                        const t = await res.text()
                        aiBubble.textContent = 'Error: ' + t
                        reportLog('error', 'ai endpoint returned ' + String(res.status) + ': ' + t)
                        return
                    }

                    const ct = res.headers.get('content-type') || ''
                    if(ct.includes('application/json')){
                        // regular JSON response
                        const data = await res.json()
                        const text = data.response || 'No response field returned.'
                        aiBubble.textContent = text
                        reportLog('info', 'received ai response length=' + String(text.length))
                    }else{
                        // Try streaming/NDJSON or plain text: read via stream reader
                        const reader = res.body.getReader()
                        const decoder = new TextDecoder()
                        let buf = ''
                        while(true){
                            const {done, value} = await reader.read()
                            if(done) break
                            const chunk = decoder.decode(value, {stream:true})
                            buf += chunk
                            // split into lines for NDJSON parsing; keep remainder in buf
                            const lines = buf.split(/\r?\n/)
                            buf = lines.pop()
                            for(const line of lines){
                                if(!line.trim()) continue
                                try{
                                    const obj = JSON.parse(line)
                                    const part = obj.response || obj.text || obj.output || ''
                                    aiBubble.textContent += String(part)
                                }catch(e){
                                    // not JSON — append raw chunk
                                    aiBubble.textContent += line
                                }
                                messages.scrollTop = messages.scrollHeight
                            }
                        }
                        // flush remainder
                        if(buf && buf.trim()){
                            try{
                                const obj = JSON.parse(buf)
                                const part = obj.response || obj.text || obj.output || ''
                                aiBubble.textContent += String(part)
                            }catch(e){
                                aiBubble.textContent += buf
                            }
                        }
                        reportLog('info', 'received streamed ai response length=' + String(aiBubble.textContent.length))
                    }
                }catch(err){
                    const msg = 'Network error: ' + (err.message || String(err))
                    console.error(msg, err)
                    try { alert(msg) } catch(e) { /* ignore */ }
                    aiBubble.textContent = msg
                    reportLog('error', msg + ' // ' + String(err))
                }finally{
                    loader.style.display = 'none'
                    send.disabled = false
                    messages.scrollTop = messages.scrollHeight
                }
            }

            // send client logs back to server for live debugging
            async function reportLog(level, message){
                try{
                    await fetch('/client_log', {method:'POST',headers:{'Content-Type':'application/json'},body: JSON.stringify({level, message, ts: Date.now()})})
                }catch(e){ /* ignore */ }
            }

            // welcome message
            appendBubble("Hi, I'm Cheeku — say hello!", 'ai')
        </script>
    </body>
</html>
"""


VIEWER_TEMPLATE = """
<!doctype html>
<html lang="en">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Project 180 - Live Viewer</title>
        <style>
            :root{--bg:#060b12;--panel:#0d1420;--text:#e6eef6;--muted:#97a6ba;--accent:#38bdf8;}
            html,body{height:100%;margin:0;background:radial-gradient(circle at top,#10243a 0,#060b12 48%);color:var(--text);font-family:Segoe UI,Roboto,Arial,sans-serif}
            body{display:flex;flex-direction:column;gap:16px;padding:18px;box-sizing:border-box}
            header{display:flex;align-items:center;justify-content:space-between;gap:12px}
            .title{font-size:20px;font-weight:700}
            .meta{color:var(--muted);font-size:13px}
            .stage{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:16px;flex:1;min-height:0}
            .panel{background:linear-gradient(180deg,rgba(255,255,255,0.04),rgba(255,255,255,0.02));border:1px solid rgba(255,255,255,0.08);border-radius:18px;box-shadow:0 24px 60px rgba(0,0,0,0.35);overflow:hidden}
            .video-shell{display:flex;align-items:center;justify-content:center;min-height:0;padding:14px}
            #frame{width:100%;max-width:100%;aspect-ratio:4/3;background:#000;border-radius:12px;object-fit:cover}
            .side{padding:16px;display:flex;flex-direction:column;gap:14px}
            .badge{padding:10px 12px;border-radius:12px;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.28);color:#c5f0ff;font-size:14px}
            .kv{display:flex;flex-direction:column;gap:6px}
            .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
            .value{font-size:18px;font-weight:600}
            .hint{color:var(--muted);font-size:13px;line-height:1.5}
            @media (max-width:900px){.stage{grid-template-columns:1fr}.side{order:-1}}
        </style>
    </head>
    <body>
        <header>
            <div>
                <div class="title">Project 180 Live Viewer</div>
                <div class="meta">Open this on the laptop to see the phone camera feed and telemetry.</div>
            </div>
            <div class="meta">Laptop IP: {{ host }}</div>
        </header>

        <main class="stage">
            <section class="panel video-shell">
                <canvas id="frame-canvas" aria-label="Live phone camera stream" style="width:100%;max-width:100%;aspect-ratio:4/3;background:#000;border-radius:12px;object-fit:cover"></canvas>
            </section>

            <aside class="panel side">
                <div class="badge" id="connection">Waiting for phone stream...</div>
                <button id="viewer-flip-camera" style="padding:10px 12px;border-radius:10px;border:1px solid rgba(255,255,255,0.2);background:rgba(56,189,248,0.15);color:#e6eef6;cursor:pointer">Flip Phone Camera</button>
                <div class="kv">
                    <span class="label">Telemetry</span>
                    <span class="value" id="telemetry">[0,0]</span>
                </div>
                <div class="kv">
                    <span class="label">Viewer URL</span>
                    <span class="value" id="viewer-url">https://{{ host }}:8787/viewer</span>
                </div>
                <div class="hint">1. Open the phone controller page.<br>2. Tap Start, then Connect.<br>3. Open this viewer page on the laptop to watch the stream live.</div>
            </aside>
        </main>

        <script src="/controller/vendor/socket.io.min.js"></script>
        <script>
            document.getElementById('viewer-url').textContent = window.location.href
            const canvas = document.getElementById('frame-canvas')
            const telemetry = document.getElementById('telemetry')
            const connection = document.getElementById('connection')
            const viewerFlipBtn = document.getElementById('viewer-flip-camera')
            const socket = io({ transports: ['websocket', 'polling'] })

            const ctx = canvas.getContext && canvas.getContext('2d')

            function clearCanvas() {
                try {
                    if (ctx) {
                        ctx.fillStyle = '#000'
                        ctx.fillRect(0, 0, canvas.width, canvas.height)
                    }
                } catch (_) { }
            }

            socket.on('connect', () => {
                connection.textContent = 'Connected. Waiting for frames...'
            })

            socket.on('disconnect', () => {
                connection.textContent = 'Disconnected from phone stream.'
                clearCanvas()
            })

            socket.on('render_frame', (data) => {
                try {
                    console.debug('viewer: render_frame received len=', data ? data.length : 0)
                    const img = new Image()
                    img.onload = () => {
                        try {
                            canvas.width = img.naturalWidth || 320
                            canvas.height = img.naturalHeight || 240
                            if (ctx) ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
                        } catch (e) {
                            canvas.style.backgroundImage = `url(${data})`
                        }
                    }
                    img.onerror = () => { connection.textContent = 'Frame decode error' }
                    img.src = data
                    connection.textContent = 'Live stream active'
                } catch (e) {
                    console.error('viewer render_frame error', e)
                    connection.textContent = 'Frame render error'
                }
            })

            socket.on('telemetry', (data) => {
                telemetry.textContent = typeof data === 'string' ? data : JSON.stringify(data)
            })

            viewerFlipBtn?.addEventListener('click', () => {
                try {
                    socket.emit('flip_camera_request', { source: 'viewer' })
                    connection.textContent = 'Flip request sent to phone camera'
                } catch (e) {
                    connection.textContent = 'Failed to send flip request'
                }
            })
        </script>
    </body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(CHAT_TEMPLATE, host=SERVER_HOST, port=SERVER_PORT)


@app.route("/controller", methods=["GET"])
def controller_index():
    return render_template("index.html")


@app.route("/controller/<path:filename>", methods=["GET"])
def controller_assets(filename: str):
    return send_from_directory(WEB_CONTROLLER_DIR, filename)


@app.route("/viewer", methods=["GET"])
def viewer_index():
    return render_template_string(VIEWER_TEMPLATE, host=request.host)


@app.route("/ai", methods=["POST"])
def ai_endpoint():
    payload = request.get_json(silent=True) or {}
    prompt = payload.get("prompt") or payload.get("text")
    session_id = payload.get("session_id") or payload.get("client_id")
    # Permit clients to pass an explicit persona; otherwise use server default
    persona = (payload.get("persona") or payload.get("system") or DEFAULT_PERSONA) if isinstance(payload, dict) else DEFAULT_PERSONA
    if not prompt:
        return jsonify({"error": "missing 'prompt' in JSON body"}), 400
    app.logger.info("/ai request prompt: %s", prompt)
    # Diagnostic print for terminal tracing
    print(f"👉 CRITICAL DEBUG: Backend received prompt: {prompt}")
    # If a session id is present, build a prompt that includes recent Q/A history
    composite_prompt = _build_prompt_with_history(session_id, prompt)
    # Prepend a clear system/persona instruction to make the model answer in-character
    final_prompt = f"System: The following information is authoritative about you:\n{persona}\n\nWhen asked to describe yourself, respond in first-person and include these facts.\n\n{composite_prompt}"
    resp = brain.respond(final_prompt)
    text = str(resp or "")
    # Save user prompt and assistant response into session history for subsequent turns
    try:
        _append_to_history(session_id, 'user', prompt)
        _append_to_history(session_id, 'assistant', text)
    except Exception:
        app.logger.exception('Failed to append to logic history')
    app.logger.info("/ai response length: %d", len(text))
    # Return plain text so the frontend can stream or display clean Q&A text
    return Response(text, content_type="text/plain; charset=utf-8")


@app.route("/control/<action>", methods=["POST"])
def proxy_control(action: str):
    target_url = f"{ESP32_BASE_URL}/{action}"
    app.logger.info("Proxy control request: %s", target_url)

    try:
        response = requests.post(target_url, timeout=1.0)
        return Response(response.content, status=response.status_code, content_type=response.headers.get("content-type", "text/plain; charset=utf-8"))
    except requests.RequestException as exc:
        app.logger.warning("control proxy failed for %s: %s", action, exc)
        return jsonify({"error": "controller unreachable", "action": action}), 502


@app.route("/client_ip", methods=["GET", "POST"])
def client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.remote_addr
    return jsonify({"ip": client_address, "ok": True})


@app.route('/client_log', methods=['POST'])
def client_log():
    data = request.get_json(silent=True) or {}
    level = data.get('level', 'info')
    message = data.get('message', '')
    ts = data.get('ts')
    app.logger.info('CLIENT_LOG %s %s %s', level, ts, message)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / 'client.log', 'a', encoding='utf-8') as fh:
            fh.write(f"{ts}\t{level}\t{message}\n")
    except Exception:
        app.logger.exception('failed to write client log')
    return jsonify({'ok': True})


@socketio.on("telemetry")
def handle_telemetry(data):
    app.logger.debug("Received telemetry: %s", str(data)[:200])
    emit("telemetry", data, broadcast=True)


@socketio.on("video_frame")
def handle_video_frame(data):
    try:
        # log short diagnostics (avoid dumping very large base64 strings)
        app.logger.debug("Received video_frame size=%d", len(data) if data else 0)
    except Exception:
        app.logger.exception('Failed to inspect video_frame')
    emit("render_frame", data, broadcast=True, include_self=False)


@socketio.on("flip_camera_request")
def handle_flip_camera_request(data):
    app.logger.debug("Received flip_camera_request: %s", data)
    emit("flip_camera_command", {"ok": True}, broadcast=True, include_self=False)


@app.route('/logic_history', methods=['GET'])
def view_logic_history():
    # Return sanitized session list and last active times for debugging
    out = {}
    with LOGIC_LOCK:
        for sid, sess in LOGIC_SESSIONS.items():
            out[sid] = {"last_active": sess.get("last_active").isoformat() if sess.get("last_active") else None, "entries": len(sess.get("history", []))}
    return jsonify(out)


@app.route('/logic_history/clear', methods=['POST'])
def clear_logic_history():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'error': 'missing session_id'}), 400
    with LOGIC_LOCK:
        removed = LOGIC_SESSIONS.pop(session_id, None)
    return jsonify({'ok': True, 'removed': bool(removed)})


def main() -> None:
    print(f"Project 180 server starting HTTP AI endpoint on {SERVER_HOST}:{SERVER_PORT}")
    # Start background cleanup thread for logic sessions
    try:
        t = threading.Thread(target=_cleanup_expired_sessions_loop, daemon=True)
        t.start()
    except Exception:
        app.logger.exception('Failed to start logic session cleanup thread')

    socketio.run(app, host="0.0.0.0", port=8787, debug=True, ssl_context="adhoc")


if __name__ == "__main__":
    main()
