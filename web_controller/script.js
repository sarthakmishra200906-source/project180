const CONNECT_TIMEOUT_MS = 4500;

const connectBtn = document.getElementById('connect-btn');
const startBtn = document.getElementById('start-btn');
const flipCameraBtn = document.getElementById('flip-camera-btn');
const espIpInput = document.getElementById('esp-ip');
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const voiceModeChip = document.getElementById('voice-mode-chip');
const clientIpText = document.getElementById('client-ip-text');
const payloadDebug = document.getElementById('payload-debug');
const cameraSource = document.getElementById('camera-source');
const videoCanvas = document.getElementById('video-canvas');
const steeringWheel = document.getElementById('steeringWheel');
const laptopBtn = document.getElementById('laptopBtn');
const mobileBtn = document.getElementById('mobileBtn');
const deviceModal = document.getElementById('deviceModal');
const laptopController = document.getElementById('laptopController');
const mobileController = document.getElementById('mobileController');
const switchBtn = document.getElementById('switchBtn');

let currentMode = null;
let socket = null;
let connectTimer = null;
let keyboardState = new Set();
let activePointerId = null;
let activeMouseDrag = false;
let currentDrive = 0;
let currentSteer = 0;
let currentSteerSign = 0;
let cameraStream = null;
let cameraFrameTimer = null;
let cameraFacingMode = 'environment';
let speechRecognition = null;
let voiceActive = false;
let voiceRestartTimer = null;
let cameraReady = false;
let socketIoLoadPromise = null;
let frameCounter = 0;
// persistent client id for session-scoped logic history
let clientId = null;

function getClientId() {
    if (clientId) return clientId;
    try {
        const key = 'project180_client_id';
        clientId = localStorage.getItem(key);
        if (!clientId) {
            // simple random id
            clientId = 'c-' + Math.random().toString(36).slice(2, 12) + '-' + Date.now().toString(36);
            try { localStorage.setItem(key, clientId); } catch (_) { /* ignore storage errors */ }
        }
    } catch (e) {
        clientId = 'c-guest-' + Date.now();
    }
    return clientId;
}

let logicMode = false;
let waitingForLogicQuery = false;
let isHandlingLogicQuery = false;
let logicAwaitTimer = null;
let lastHeardText = '';
let lastHeardAt = 0;
let qaLanguage = 'en';
let preferredResponseStyle = 'auto';

const listeningBadge = document.getElementById('listening-badge');

const canvasContext = videoCanvas ? videoCanvas.getContext('2d') : null;

if (flipCameraBtn) {
    flipCameraBtn.disabled = true;
}

if (espIpInput && !espIpInput.value) {
    espIpInput.value = window.location.hostname || '';
}

const driveInputs = new Map();
const steerInputs = new Map();

const keyBindings = {
    w: { axis: 'drive', value: 100, action: 'forward' },
    arrowup: { axis: 'drive', value: 100, action: 'forward' },
    s: { axis: 'drive', value: -100, action: 'backward' },
    arrowdown: { axis: 'drive', value: -100, action: 'backward' },
    a: { axis: 'steer', value: -90, action: 'left' },
    arrowleft: { axis: 'steer', value: -90, action: 'left' },
    d: { axis: 'steer', value: 90, action: 'right' },
    arrowright: { axis: 'steer', value: 90, action: 'right' },
};

function setConnectionState(state) {
    statusIndicator.classList.remove('disconnected', 'connecting', 'connected');
    statusIndicator.classList.add(state);
}

function setDisconnected(message = 'Disconnected') {
    if (connectTimer) {
        clearTimeout(connectTimer);
        connectTimer = null;
    }
    setConnectionState('disconnected');
    statusText.textContent = message;
    connectBtn.textContent = 'Connect';
}

function setConnecting() {
    setConnectionState('connecting');
    statusText.textContent = 'Connecting...';
    connectBtn.textContent = 'Connecting...';
}

function setConnected() {
    setConnectionState('connected');
    statusText.textContent = 'Connected to Cheeku';
    connectBtn.textContent = 'Disconnect';
}

function showClientIp(ip) {
    if (clientIpText) {
        clientIpText.textContent = ip ? `Detected phone IP: ${ip}` : '';
    }
}

function stopCameraStream() {
    if (cameraFrameTimer) {
        clearInterval(cameraFrameTimer);
        cameraFrameTimer = null;
    }

    if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
        cameraStream = null;
    }

    if (cameraSource) {
        cameraSource.srcObject = null;
    }

    cameraReady = false;
}

function stopVoiceRecognition() {
    voiceActive = false;

    if (voiceRestartTimer) {
        clearTimeout(voiceRestartTimer);
        voiceRestartTimer = null;
    }

    if (speechRecognition) {
        try {
            speechRecognition.onresult = null;
            speechRecognition.onend = null;
            speechRecognition.onerror = null;
            speechRecognition.stop();
        } catch (_) {
            // ignore
        }
        speechRecognition = null;
    }
    // hide listening badge and reset logic mode when stopping
    if (listeningBadge) {
        listeningBadge.style.display = 'none';
    }
    logicMode = false;
    waitingForLogicQuery = false;
    isHandlingLogicQuery = false;
    clearLogicAwaitWindow();
}

function closeSocketConnection() {
    if (connectTimer) {
        clearTimeout(connectTimer);
        connectTimer = null;
    }

    const activeSocket = socket;
    socket = null;

    if (activeSocket) {
        try {
            activeSocket.disconnect();
        } catch (_) {
            // ignore
        }
    }

    stopCameraStream();
    stopVoiceRecognition();
    setDisconnected();
}

startBtn?.addEventListener('click', async () => {
    try {
        const response = await fetch('/client_ip', { method: 'POST' });
        if (!response.ok) {
            throw new Error(`IP lookup failed with status ${response.status}`);
        }

        const data = await response.json();
        showClientIp(data.ip || 'unknown');
    } catch (error) {
        console.error('Client IP lookup failed', error);
        showClientIp('unavailable');
    }
});

const ttsTestBtn = document.getElementById('tts-test-btn');
ttsTestBtn?.addEventListener('click', () => {
    speakText('This is a short audio test. If you hear this, text to speech is working.');
});

// When the user taps Start, also proactively request camera+mic permissions
startBtn?.addEventListener('click', async () => {
    // user gesture — request both permissions so camera/mic prompts appear
    try {
        const ok = await requestMediaAccess({ video: true, audio: true });
        if (!ok) {
            alert('Please allow camera and microphone access for full functionality.');
        } else {
            // optional: provide feedback
            updateConnectionLabel('Media permissions granted');
        }
    } catch (e) {
        console.warn('Permission request failed', e);
    }
});

// Request camera/microphone access (called on user gesture to trigger browser prompt)
async function requestMediaAccess({ video = false, audio = false } = {}) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return false;
    }

    const constraints = {};
    if (video) constraints.video = { width: 320, height: 240 };
    if (audio) constraints.audio = true;

    try {
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        // stop tracks immediately; we only wanted permission prompt
        try {
            stream.getTracks().forEach((t) => t.stop());
        } catch (_) { }
        return true;
    } catch (err) {
        console.warn('Media permission request failed', err);
        return false;
    }
}

function getSocketServerUrl() {
    return window.location.origin;
}

function emitTelemetry() {
    const payload = `[${currentDrive},${currentSteer}]`;
    if (payloadDebug) payloadDebug.textContent = payload;

    if (socket && socket.connected) {
        try {
            socket.emit('telemetry', payload);
        } catch (_) {
            // ignore send issues
        }
    }
}

function emitFrame(frameData) {
    if (socket && socket.connected) {
        try {
            socket.emit('video_frame', frameData);
            frameCounter += 1;
            if (payloadDebug) payloadDebug.textContent = `frames:${frameCounter}`;
            console.debug('emitFrame sent frames=', frameCounter, 'size=', frameData ? frameData.length : 0)
        } catch (err) {
            console.warn('emitFrame error', err)
        }
    }
}

function loadSocketIoClient() {
    if (typeof window.io === 'function') {
        return Promise.resolve();
    }

    if (socketIoLoadPromise) {
        return socketIoLoadPromise;
    }

    socketIoLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/controller/vendor/socket.io.min.js';
        script.defer = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Socket.IO client failed to load'));
        document.head.appendChild(script);
    });

    return socketIoLoadPromise;
}

function updateConnectionLabel(message) {
    if (payloadDebug) {
        payloadDebug.textContent = message;
    }
}

function maybeResizeCanvas() {
    if (!videoCanvas) {
        return;
    }

    const width = 320;
    const height = 240;
    if (videoCanvas.width !== width) {
        videoCanvas.width = width;
    }
    if (videoCanvas.height !== height) {
        videoCanvas.height = height;
    }
}

async function startCamera(facingMode) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        updateConnectionLabel('Camera not supported in this browser.');
        return;
    }

    stopCameraStream();
    maybeResizeCanvas();

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: { ideal: facingMode },
                width: { ideal: 320 },
                height: { ideal: 240 },
            },
            audio: false,
        });

        cameraStream = stream;
        cameraFacingMode = facingMode;
        cameraReady = true;

        if (cameraSource) {
            cameraSource.srcObject = stream;
            cameraSource.muted = true;
            cameraSource.playsInline = true;
            await cameraSource.play().catch(() => { });
        }

        if (cameraFrameTimer) {
            clearInterval(cameraFrameTimer);
        }

        cameraFrameTimer = setInterval(() => {
            if (!cameraStream || !cameraSource || !canvasContext || !videoCanvas) {
                return;
            }

            if (cameraSource.readyState < 2) {
                return;
            }

            if (cameraSource.videoWidth === 0 || cameraSource.videoHeight === 0) {
                return;
            }

            maybeResizeCanvas();
            canvasContext.drawImage(cameraSource, 0, 0, videoCanvas.width, videoCanvas.height);
            const frameData = videoCanvas.toDataURL('image/jpeg', 0.4);
            emitFrame(frameData);
        }, 100);
    } catch (error) {
        cameraReady = false;
        updateConnectionLabel('Camera access blocked or unavailable.');
        console.error('Camera start failed', error);
    }
}

function speakText(text) {
    if (!text) {
        return;
    }

    try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = qaLanguage === 'hi' ? 'hi-IN' : 'en-IN';
        window.speechSynthesis.speak(utterance);
    } catch (error) {
        console.error('Speech synthesis failed', error);
    }
}

function getRecognitionLanguage(style = preferredResponseStyle) {
    return style === 'hi' ? 'hi-IN' : 'en-IN';
}

function getResponseStyleLabel(style = preferredResponseStyle) {
    if (style === 'hi') return 'Hindi';
    if (style === 'hinglish') return 'Hinglish';
    if (style === 'en') return 'English';
    return 'Default';
}

function updateVoiceModeChip(style = preferredResponseStyle) {
    if (!voiceModeChip) {
        return;
    }

    voiceModeChip.textContent = `MODE: ${getResponseStyleLabel(style)}`;
}

function updateListeningBadge(text) {
    if (!listeningBadge) {
        return;
    }

    listeningBadge.style.display = 'inline-block';
    listeningBadge.textContent = text || `LISTENING (${getResponseStyleLabel()})`;
}

function clearLogicAwaitWindow() {
    if (logicAwaitTimer) {
        clearTimeout(logicAwaitTimer);
        logicAwaitTimer = null;
    }
}

function armLogicAwaitWindow() {
    clearLogicAwaitWindow();
    logicAwaitTimer = setTimeout(() => {
        waitingForLogicQuery = false;
        logicMode = false;
        if (voiceActive) {
            updateListeningBadge(`LISTENING (${getResponseStyleLabel()})`);
        }
    }, 7000);
}

function setPreferredResponseStyle(style) {
    preferredResponseStyle = style || 'auto';
    qaLanguage = preferredResponseStyle === 'hi' ? 'hi' : 'en';

    if (speechRecognition) {
        speechRecognition.lang = getRecognitionLanguage();
    }

    updateVoiceModeChip();
    updateListeningBadge(`LISTENING (${getResponseStyleLabel()})`);
}

function detectResponseStyle(text) {
    const value = String(text || '').trim().toLowerCase();
    if (!value) {
        return 'en';
    }

    if (/[\u0900-\u097f]/.test(value)) {
        return 'hi';
    }

    const hindiTokens = new Set([
        'kya', 'kyun', 'kyoon', 'ka', 'ki', 'ke', 'hai', 'hain', 'ho', 'haan', 'nahi', 'nahi', 'mat',
        'mujhe', 'mera', 'meri', 'mere', 'tum', 'aap', 'ham', 'hum', 'ek', 'do', 'teen', 'chaar',
        'sunao', 'sunayo', 'sunana', 'batao', 'batado', 'bata', 'majadar', 'majedar', 'mazedar', 'khabar',
        'baat', 'bat', 'accha', 'achha', 'aaj', 'kal', 'abhi', 'thoda', 'zyada', 'bahut', 'samjhao'
    ]);

    const englishTokens = new Set([
        'what', 'why', 'how', 'when', 'where', 'temperature', 'weather', 'joke', 'crack', 'tell', 'jokes',
        'answer', 'language', 'switch', 'english', 'hindi', 'hinglish', 'give', 'me', 'the', 'is', 'are'
    ]);

    const tokens = value.replace(/[^a-z\s]/g, ' ').split(/\s+/).filter(Boolean);
    let hindiCount = 0;
    let englishCount = 0;

    for (const token of tokens) {
        if (hindiTokens.has(token)) {
            hindiCount += 1;
        }
        if (englishTokens.has(token)) {
            englishCount += 1;
        }
    }

    if (hindiCount > 0 && englishCount > 0) {
        return 'hinglish';
    }

    if (hindiCount > 0) {
        return 'hi';
    }

    return 'en';
}

function extractLanguageCommand(text) {
    const value = String(text || '').toLowerCase().trim();
    if (!value) {
        return null;
    }

    const compact = value.replace(/[^a-z\s]/g, ' ').replace(/\s+/g, ' ').trim();
    const exactWord = compact.match(/^(hindi|hinglish|english|eng)$/);
    if (exactWord) {
        const word = exactWord[1];
        return word === 'hindi' ? 'hi' : word === 'hinglish' ? 'hinglish' : 'en';
    }

    const switchMatch = compact.match(/^(?:switch|set|change)\s+(?:to\s+)?(hindi|hinglish|english|eng)(?:\s+mode)?$/);
    if (switchMatch) {
        const word = switchMatch[1];
        return word === 'hindi' ? 'hi' : word === 'hinglish' ? 'hinglish' : 'en';
    }

    const modeMatch = compact.match(/^(hindi|hinglish|english|eng)\s+mode$/);
    if (modeMatch) {
        const word = modeMatch[1];
        return word === 'hindi' ? 'hi' : word === 'hinglish' ? 'hinglish' : 'en';
    }

    if (/^only\s+hindi$/.test(compact)) {
        return 'hi';
    }

    if (/^only\s+hinglish$/.test(compact)) {
        return 'hinglish';
    }

    if (/^only\s+english$/.test(compact)) {
        return 'en';
    }

    return null;
}

function buildPromptForStyle(prompt, style) {
    const normalizedStyle = style || 'auto';
    if (normalizedStyle === 'hi') {
        return `Answer only in Hindi using Devanagari script. Do not use English unless absolutely required.\nUser question: ${prompt}`;
    }
    if (normalizedStyle === 'hinglish') {
        return `Answer only in Hinglish using Roman script with simple Hindi-English mix. Keep the answer natural and conversational.\nUser question: ${prompt}`;
    }
    if (normalizedStyle === 'en') {
        return `Answer only in English. Do not translate into Hindi.\nUser question: ${prompt}`;
    }
    return `Answer in the same language and script as the user's question. If the question is Hinglish, answer in Hinglish. If Hindi, answer in Hindi. If English, answer in English.\nUser question: ${prompt}`;
}

function getPersonaPrefix() {
    try {
        const stored = localStorage.getItem('project180_persona');
        if (stored && stored.trim()) return stored.trim();
    } catch (_) { }
    // default persona: concise, friendly companion AI
    return "You are Cheeku, a friendly, concise companion robot. Answer in-character and speak as Cheeku when asked to describe yourself.";
}

function resolveStyleForQuestion(question) {
    if (preferredResponseStyle !== 'auto') {
        return preferredResponseStyle;
    }

    return detectResponseStyle(question);
}

async function handleKnowledgeQuery(prompt, styleOverride = null) {
    try {
        const resolvedStyle = styleOverride || resolveStyleForQuestion(prompt);
        qaLanguage = resolvedStyle === 'hi' ? 'hi' : 'en';
        updateVoiceModeChip(resolvedStyle);
        // Prepend persona/system instruction so the model answers in-character
        const persona = getPersonaPrefix();
        const finalPrompt = persona + "\n\n" + buildPromptForStyle(prompt, resolvedStyle);
        const response = await fetch('/ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: finalPrompt, session_id: getClientId(), persona }),
        });

        if (!response.ok) {
            throw new Error(`AI request failed with status ${response.status}`);
        }

        const answer = await response.text();
        // show answer text for visual feedback and speak
        if (payloadDebug) payloadDebug.textContent = `AI: ${answer.slice(0, 200)}`;
        console.debug('AI answer length=', answer.length)
        speakText(answer);
    } catch (error) {
        console.error('Knowledge query failed', error);
    }
}

function sanitizeQuestion(text) {
    return text
        .replace(/\b(please|now|okay|ok)\b/gi, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function setVoiceLanguageFromSpeech(spoken) {
    const requested = extractLanguageCommand(spoken);
    if (requested) {
        setPreferredResponseStyle(requested);
        speakText(`Language switched to ${getResponseStyleLabel(requested)}.`);
        return true;
    }
    return false;
}

async function runLogicQuery(question) {
    const cleanQuestion = sanitizeQuestion(question);
    if (!cleanQuestion || isHandlingLogicQuery) {
        return;
    }

    isHandlingLogicQuery = true;
    clearLogicAwaitWindow();
    if (listeningBadge) {
        listeningBadge.style.display = 'inline-block';
        listeningBadge.textContent = 'CONFIRMED';
    }
    updateVoiceModeChip(resolveStyleForQuestion(cleanQuestion));
    speakText('Confirmed.');

    const styleForQuestion = resolveStyleForQuestion(cleanQuestion);
    await handleKnowledgeQuery(cleanQuestion, styleForQuestion);

    waitingForLogicQuery = false;
    logicMode = false;
    isHandlingLogicQuery = false;
    if (listeningBadge) {
        updateListeningBadge(`LISTENING (${getResponseStyleLabel()})`);
    }
}

function initializeSpeechRecognition() {
    const SpeechRecognition = window.webkitSpeechRecognition || window.SpeechRecognition;
    if (!SpeechRecognition || speechRecognition) {
        return;
    }

    speechRecognition = new SpeechRecognition();
    speechRecognition.continuous = true;
    speechRecognition.lang = getRecognitionLanguage();
    speechRecognition.interimResults = false;

    updateVoiceModeChip();

    speechRecognition.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
            const result = event.results[i];
            if (!result?.isFinal) continue;

            const transcript = (result[0]?.transcript || '').trim();
            if (!transcript) continue;

            const spoken = transcript.toLowerCase();
            const now = Date.now();

            // suppress duplicated final recognition bursts
            if (spoken === lastHeardText && now - lastHeardAt < 1500) {
                continue;
            }
            lastHeardText = spoken;
            lastHeardAt = now;

            const includesMovement = /\b(forward|reverse|backward|stop|left|right)\b/.test(spoken);
            if (includesMovement) {
                if (/\bstop\b/.test(spoken)) {
                    currentDrive = 0;
                    currentSteer = 0;
                } else {
                    if (/\bforward\b/.test(spoken)) currentDrive = 100;
                    if (/\breverse\b|\bbackward\b/.test(spoken)) currentDrive = -100;
                    if (/\bleft\b/.test(spoken)) currentSteer = -90;
                    if (/\bright\b/.test(spoken)) currentSteer = 90;
                }
                emitTelemetry();
                syncButtonStates();
                continue;
            }

            // language switch commands work in both laptop/mobile modes
            if (setVoiceLanguageFromSpeech(spoken)) {
                continue;
            }

            if (/\b(exit logic|stop listening|cancel)\b/.test(spoken)) {
                waitingForLogicQuery = false;
                logicMode = false;
                clearLogicAwaitWindow();
                if (listeningBadge) listeningBadge.textContent = 'LISTENING (say logic)';
                speakText('Logic cancelled. Say logic when ready.');
                continue;
            }

            // Require "logic" for every question.
            if (/\blogic\b/.test(spoken)) {
                logicMode = true;
                waitingForLogicQuery = true;
                armLogicAwaitWindow();
                if (listeningBadge) {
                    listeningBadge.style.display = 'inline-block';
                    listeningBadge.textContent = 'LOGIC READY';
                }

                const trailing = sanitizeQuestion(spoken.split(/\blogic\b/i).slice(1).join(' '));
                if (trailing) {
                    runLogicQuery(trailing);
                } else {
                    speakText('Confirmed. Ask your question.');
                }
                continue;
            }

            if (waitingForLogicQuery) {
                armLogicAwaitWindow();
                runLogicQuery(spoken);
                continue;
            }

            // If user asks without logic, keep calm and wait for wake word.
            if (listeningBadge) {
                listeningBadge.style.display = 'inline-block';
                listeningBadge.textContent = 'Say LOGIC first';
            }
        }
    };

    speechRecognition.onerror = (event) => {
        console.warn('Speech recognition error', event.error);
    };

    speechRecognition.onend = () => {
        if (voiceActive) {
            if (voiceRestartTimer) {
                clearTimeout(voiceRestartTimer);
            }

            voiceRestartTimer = setTimeout(() => {
                try {
                    speechRecognition?.start();
                } catch (_) {
                    // ignore restart errors
                }
            }, 300);
        }
    };
}

function startVoiceRecognition() {
    if (voiceActive) {
        return;
    }

    initializeSpeechRecognition();
    if (!speechRecognition) {
        return;
    }

    // Ensure microphone permission is granted via a prompt before starting
    voiceActive = true;
    (async () => {
        const ok = await requestMediaAccess({ audio: true });
        if (!ok) {
            voiceActive = false;
            alert('Microphone access is required for voice commands. Please allow microphone access.');
            return;
        }

        try {
            updateVoiceModeChip();
            if (listeningBadge) {
                updateListeningBadge(`LISTENING (${getResponseStyleLabel()})`);
            }
            speechRecognition.lang = getRecognitionLanguage();
            speechRecognition.start();
        } catch (error) {
            voiceActive = false;
            console.warn('Unable to start speech recognition', error);
        }
    })();
}

function stopAllMedia() {
    stopCameraStream();
    stopVoiceRecognition();
}

function resolveAxisValue(inputs) {
    const values = Array.from(inputs.values());
    if (values.length === 0) {
        return 0;
    }

    return values.reduce((strongest, value) => {
        return Math.abs(value) > Math.abs(strongest) ? value : strongest;
    }, 0);
}

function resolveSteerValue(inputs) {
    const values = Array.from(inputs.values());
    if (values.length === 0) {
        currentSteerSign = 0;
        return 0;
    }

    const strongest = values.reduce((best, value) => {
        return Math.abs(value) > Math.abs(best) ? value : best;
    }, 0);

    currentSteerSign = strongest === 0 ? 0 : Math.sign(strongest);
    return strongest;
}

function syncButtonStates() {
    const forwardActive = currentDrive > 0;
    const backwardActive = currentDrive < 0;
    const leftActive = currentSteer < 0;
    const rightActive = currentSteer > 0;

    document.querySelectorAll('[data-action]').forEach((button) => {
        const action = button.dataset.action;
        if (!action) {
            return;
        }

        const shouldBeActive = action === 'forward' ? forwardActive
            : action === 'backward' ? backwardActive
                : action === 'left' ? leftActive
                    : action === 'right' ? rightActive
                        : false;

        button.classList.toggle('active', shouldBeActive);
    });
}

function setSteerState(rawSteer) {
    currentSteer = Math.max(-90, Math.min(90, Math.round(rawSteer)));
    currentSteerSign = currentSteer === 0 ? 0 : Math.sign(currentSteer);
}

function computeWheelSteer(clientX, clientY) {
    const center = getWheelCenter();
    const dx = clientX - center.x;
    const dy = clientY - center.y;

    const distance = Math.sqrt((dx * dx) + (dy * dy));
    const wheelRadius = Math.min(steeringWheel.offsetWidth, steeringWheel.offsetHeight) / 2;
    const normalizedDistance = wheelRadius > 0 ? Math.min(1, distance / wheelRadius) : 0;

    // 0..90 magnitude that grows as the drag moves away from the center.
    const magnitude = Math.round(normalizedDistance * 90);

    // Determine left/right sign from the horizontal side of the wheel.
    const sign = dx === 0 ? (currentSteerSign || 1) : Math.sign(dx);
    return Math.max(-90, Math.min(90, magnitude * sign));
}

function syncControlPacket() {
    currentDrive = resolveAxisValue(driveInputs);
    currentSteer = resolveSteerValue(steerInputs);
    transmitData();
    syncButtonStates();
}

function clearControlInputs() {
    driveInputs.clear();
    steerInputs.clear();
    currentDrive = 0;
    currentSteer = 0;
    currentSteerSign = 0;
    transmitData();
    syncButtonStates();
}

function transmitData() {
    emitTelemetry();
}

function getWheelCenter() {
    const rect = steeringWheel.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

function updateKeyVisual(action, on) {
    document.querySelectorAll(`[data-action="${action}"]`).forEach((el) => {
        el.classList.toggle('active', on);
        el.classList.toggle('pressed', on);
    });
}

function normalizeWheelAngle(rawAngle) {
    // rawAngle is based on atan2 with 0 at the right; shift so 0 is up.
    let angle = rawAngle + 90;
    if (angle > 180) angle -= 360;
    if (angle < -180) angle += 360;
    return Math.max(-90, Math.min(90, angle));
}

function applyWheelRotation(angle) {
    steeringWheel.style.transform = `rotate(${angle}deg)`;
}

connectBtn?.addEventListener('click', async () => {
    if (socket && socket.connected) {
        closeSocketConnection();
        return;
    }

    const targetIp = (espIpInput?.value || '').trim();
    if (!targetIp) {
        alert('Please enter the target ESP32 IP address.');
        return;
    }

    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
        alert('Open the controller page with https://192.168.31.100:8787/controller so the browser can ask for camera and microphone permissions.');
        return;
    }

    setConnecting();

    try {
        await loadSocketIoClient();

        socket = window.io(getSocketServerUrl(), { transports: ['websocket', 'polling'] });
    } catch (error) {
        socket = null;
        setDisconnected();
        const message = error && error.message === 'Socket.IO client failed to load'
            ? 'Connection Failure: Could not load the controller networking library.'
            : 'Connection Failure: Laptop server is not reachable on the local network.';
        alert(message);
        return;
    }

    connectTimer = setTimeout(() => {
        if (!socket || !socket.connected) {
            closeSocketConnection();
            alert('Connection Failure: Target ESP32 Device Not Available on Local Network.');
        }
    }, CONNECT_TIMEOUT_MS);

    socket.on('connect', () => {
        if (connectTimer) {
            clearTimeout(connectTimer);
            connectTimer = null;
        }
        setConnected();
    });

    socket.on('disconnect', () => {
        closeSocketConnection();
    });

    socket.on('connect_error', (error) => {
        console.error('Socket.IO connection error', error);
        closeSocketConnection();
        alert('Connection Failure: Laptop server is not reachable on the local network.');
    });

    socket.on('telemetry', (data) => {
        if (payloadDebug) {
            payloadDebug.textContent = typeof data === 'string' ? data : JSON.stringify(data);
        }
    });

    socket.on('flip_camera_command', async () => {
        try {
            if (currentMode === 'mobile') {
                await flipCameraLocally();
                if (payloadDebug) payloadDebug.textContent = 'Camera flipped from laptop';
            }
        } catch (e) {
            console.warn('Remote flip camera failed', e);
        }
    });

    if (currentMode === 'mobile') {
        startCamera(cameraFacingMode);
        startVoiceRecognition();
    }
});

// Device selection modal
function selectDevice(mode) {
    try {
        if (deviceModal) {
            deviceModal.classList.add('hidden');
            // ensure modal no longer intercepts pointer events
            deviceModal.style.pointerEvents = 'none';
        }
        switchToMode(mode);
    } catch (e) {
        console.error('selectDevice error', e);
        try { if (payloadDebug) payloadDebug.textContent = 'selectDevice error: ' + String(e); } catch (_) { }
    }
}

if (laptopBtn) {
    try { laptopBtn.addEventListener('click', () => selectDevice('laptop')); } catch (_) { laptopBtn.onclick = () => selectDevice('laptop'); }
}
if (mobileBtn) {
    try { mobileBtn.addEventListener('click', () => selectDevice('mobile')); } catch (_) { mobileBtn.onclick = () => selectDevice('mobile'); }
}

// Auto-select device mode on small/touch devices to avoid leaving modal un-dismissed
if (!currentMode) {
    try {
        const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0 || window.innerWidth < 900;
        // show modal for non-touch large screens, otherwise auto-select mobile for touch devices
        if (isTouch) {
            if (deviceModal) {
                deviceModal.classList.add('hidden');
                deviceModal.style.pointerEvents = 'none';
            }
            switchToMode('mobile');
        } else {
            // leave modal visible on desktop so user can choose laptop/mobile
            if (deviceModal) {
                deviceModal.classList.remove('hidden');
                deviceModal.style.pointerEvents = 'auto';
            }
        }
    } catch (_) { }
}

switchBtn?.addEventListener('click', () => {
    switchToMode(currentMode === 'laptop' ? 'mobile' : 'laptop');
});

function switchToMode(mode) {
    currentMode = mode;
    stopCameraStream();
    if (flipCameraBtn) {
        flipCameraBtn.disabled = mode !== 'mobile';
    }
    if (mode === 'laptop') {
        laptopController.classList.remove('hidden');
        mobileController.classList.add('hidden');
        switchBtn.textContent = 'Switch to Mobile';
    } else {
        laptopController.classList.add('hidden');
        mobileController.classList.remove('hidden');
        switchBtn.textContent = 'Switch to Laptop';
    }
    switchBtn.classList.remove('hidden');
    keyboardState.clear();
    clearControlInputs();
    document.querySelectorAll('.pressed').forEach((el) => {
        el.classList.remove('pressed');
    });
    if (steeringWheel) {
        steeringWheel.style.transition = 'transform 320ms cubic-bezier(0.22, 1, 0.36, 1)';
        applyWheelRotation(0);
    }

    // Start local features on mode switch — allow using the page as a mobile controller
    // even when not connected to a remote socket. getUserMedia requires a user gesture
    // (click), and switching mode is a direct user action so it's safe to request.
    try {
        startVoiceRecognition();
    } catch (e) {
        console.warn('startVoiceRecognition failed during mode switch', e);
    }

    if (mode === 'mobile') {
        try {
            startCamera(cameraFacingMode);
        } catch (e) {
            console.warn('startCamera failed during mode switch', e);
            stopCameraStream();
        }
    } else {
        stopCameraStream();
    }
}

function startFeaturesForCurrentMode() {
    if (socket && socket.connected) {
        startVoiceRecognition();
        if (currentMode === 'mobile') {
            startCamera(cameraFacingMode);
        } else {
            stopCameraStream();
        }
    }
}

async function flipCameraLocally() {
    cameraFacingMode = cameraFacingMode === 'environment' ? 'user' : 'environment';
    if (socket && socket.connected && currentMode === 'mobile') {
        await startCamera(cameraFacingMode);
    }
}

flipCameraBtn?.addEventListener('click', async () => {
    startFeaturesForCurrentMode();
    await flipCameraLocally();
});

// Steering wheel drag: pointer events support both mouse and touch in desktop/mobile browsers.
if (steeringWheel) {
    const startWheelDrag = (clientX, clientY) => {
        steeringWheel.style.transition = 'none';
        steeringWheel.classList.add('is-dragging');

        const clamped = computeWheelSteer(clientX, clientY);
        applyWheelRotation(clamped);
        steerInputs.set('wheel', Math.round(clamped));
        syncControlPacket();
    };

    const updateWheelDrag = (clientX, clientY) => {
        const clamped = computeWheelSteer(clientX, clientY);
        applyWheelRotation(clamped);
        steerInputs.set('wheel', Math.round(clamped));
        syncControlPacket();
    };

    const endWheelDrag = () => {
        steeringWheel.classList.remove('is-dragging');
        steeringWheel.style.transition = 'transform 600ms cubic-bezier(0.22, 1, 0.36, 1)';
        applyWheelRotation(0);
        steerInputs.delete('wheel');
        currentSteerSign = 0;
        syncControlPacket();
    };

    steeringWheel.addEventListener('pointerdown', (e) => {
        if (activePointerId !== null) return;

        activePointerId = e.pointerId;
        startWheelDrag(e.clientX, e.clientY);

        try {
            steeringWheel.setPointerCapture(e.pointerId);
        } catch (_) {
            // Pointer capture may not be available in every browser state.
        }

        e.preventDefault();
    }, { passive: false });

    steeringWheel.addEventListener('pointermove', (e) => {
        if (activePointerId !== e.pointerId) return;
        updateWheelDrag(e.clientX, e.clientY);
        e.preventDefault();
    }, { passive: false });

    const releasePointerWheel = (e) => {
        if (activePointerId !== e.pointerId) return;
        activePointerId = null;
        endWheelDrag();

        try {
            steeringWheel.releasePointerCapture(e.pointerId);
        } catch (_) {
            // ignore
        }
    };

    steeringWheel.addEventListener('pointerup', releasePointerWheel, { passive: false });
    steeringWheel.addEventListener('pointercancel', releasePointerWheel, { passive: false });

    // Mouse fallback for environments where automated desktop mouse input does not emit pointer events.
    steeringWheel.addEventListener('mousedown', (e) => {
        if (activeMouseDrag) return;
        activePointerId = null;
        activeMouseDrag = true;
        startWheelDrag(e.clientX, e.clientY);
        e.preventDefault();
    });

    window.addEventListener('mousemove', (e) => {
        if (!activeMouseDrag) return;
        updateWheelDrag(e.clientX, e.clientY);
        e.preventDefault();
    });

    window.addEventListener('mouseup', () => {
        if (!activeMouseDrag) return;
        activeMouseDrag = false;
        endWheelDrag();
    });
}

// Desktop keyboard controls
window.addEventListener('keydown', (e) => {
    const key = e.key.toLowerCase();
    const binding = keyBindings[key];
    if (!binding) return;
    if (e.repeat) return;

    keyboardState.add(key);
    updateKeyVisual(binding.action, true);
    if (binding.axis === 'drive') {
        driveInputs.set(`key:${key}`, binding.value);
    } else {
        steerInputs.set(`key:${key}`, binding.value);
    }
    syncControlPacket();
    e.preventDefault();
});

window.addEventListener('keyup', (e) => {
    const key = e.key.toLowerCase();
    const binding = keyBindings[key];
    if (!binding) return;

    keyboardState.delete(key);
    updateKeyVisual(binding.action, false);
    if (binding.axis === 'drive') {
        driveInputs.delete(`key:${key}`);
    } else {
        steerInputs.delete(`key:${key}`);
    }
    syncControlPacket();
    e.preventDefault();
});

window.addEventListener('blur', () => {
    keyboardState.clear();
    activePointerId = null;
    activeMouseDrag = false;
    document.querySelectorAll('.pressed').forEach((el) => {
        el.classList.remove('pressed');
    });
    if (steeringWheel) {
        steeringWheel.style.transition = 'transform 600ms cubic-bezier(0.22, 1, 0.36, 1)';
        applyWheelRotation(0);
    }
    clearControlInputs();
});

// Tap/click controls for laptop + mobile buttons.
document.addEventListener('pointerdown', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest('[data-action]');
    if (!button) return;

    const action = button.dataset.action;
    if (!action) return;

    button.classList.add('pressed');
    if (action === 'stop') {
        driveInputs.clear();
        steerInputs.clear();
        currentDrive = 0;
        currentSteer = 0;
        syncControlPacket();
    } else if (action === 'forward') {
        driveInputs.set(`button:${action}:${event.pointerId}`, 100);
        syncControlPacket();
    } else if (action === 'backward') {
        driveInputs.set(`button:${action}:${event.pointerId}`, -100);
        syncControlPacket();
    } else if (action === 'left') {
        steerInputs.set(`button:${action}:${event.pointerId}`, -90);
        syncControlPacket();
    } else if (action === 'right') {
        steerInputs.set(`button:${action}:${event.pointerId}`, 90);
        syncControlPacket();
    }
}, { passive: true });

document.addEventListener('pointerup', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest('[data-action]');
    if (!button) return;

    const action = button.dataset.action;
    if (!action) return;

    button.classList.remove('pressed');
    if (action === 'forward' || action === 'backward') {
        driveInputs.delete(`button:${action}:${event.pointerId}`);
        syncControlPacket();
    } else if (action === 'left' || action === 'right') {
        steerInputs.delete(`button:${action}:${event.pointerId}`);
        syncControlPacket();
    }
}, { passive: true });

// Expose for debugging in console.
window.__transmitData = transmitData;
