"""Project 180 server: simple HTTP wrapper around the AI brain with a mobile UI."""

from pathlib import Path

from flask import Flask, request, jsonify, render_template_string, Response, send_from_directory
import requests
from server.core.ai_brain import AIBrain
from server.config import SERVER_HOST, SERVER_PORT, ESP32_BASE_URL


app = Flask(__name__)
brain = AIBrain()
app.logger.setLevel(10)
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
WEB_CONTROLLER_DIR = Path(__file__).resolve().parents[1] / "web_controller"


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
                    const res = await fetch('/ai', {method:'POST',headers:{'Content-Type':'application/json'},body: JSON.stringify({prompt})})
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


@app.route("/", methods=["GET"])
def index():
    return render_template_string(CHAT_TEMPLATE, host=SERVER_HOST, port=SERVER_PORT)


@app.route("/controller", methods=["GET"])
def controller_index():
    return send_from_directory(WEB_CONTROLLER_DIR, "index.html")


@app.route("/controller/<path:filename>", methods=["GET"])
def controller_assets(filename: str):
    return send_from_directory(WEB_CONTROLLER_DIR, filename)


@app.route("/ai", methods=["POST"])
def ai_endpoint():
    payload = request.get_json(silent=True) or {}
    prompt = payload.get("prompt") or payload.get("text")
    if not prompt:
        return jsonify({"error": "missing 'prompt' in JSON body"}), 400
    app.logger.info("/ai request prompt: %s", prompt)
    # Diagnostic print for terminal tracing
    print(f"👉 CRITICAL DEBUG: Backend received prompt: {prompt}")
    resp = brain.respond(prompt)
    text = str(resp or "")
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


def main() -> None:
    print(f"Project 180 server starting HTTP AI endpoint on {SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    main()
