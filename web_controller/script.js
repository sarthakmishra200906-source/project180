const CONNECT_TIMEOUT_MS = 4500;

const connectBtn = document.getElementById('connect-btn');
const espIpInput = document.getElementById('esp-ip');
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const payloadDebug = document.getElementById('payload-debug');
const steeringWheel = document.getElementById('steeringWheel');
const laptopBtn = document.getElementById('laptopBtn');
const mobileBtn = document.getElementById('mobileBtn');
const deviceModal = document.getElementById('deviceModal');
const laptopController = document.getElementById('laptopController');
const mobileController = document.getElementById('mobileController');
const switchBtn = document.getElementById('switchBtn');

let currentMode = null;
let ws = null;
let connectTimer = null;
let keyboardState = new Set();
let activePointerId = null;
let activeMouseDrag = false;
let currentDrive = 0;
let currentSteer = 0;
let currentSteerSign = 0;

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

function closeWebSocket() {
    if (connectTimer) {
        clearTimeout(connectTimer);
        connectTimer = null;
    }
    if (ws) {
        try { ws.close(); } catch (_) { /* ignore */ }
        ws = null;
    }
    setDisconnected();
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
    const payload = `[${currentDrive},${currentSteer}]`;
    if (payloadDebug) payloadDebug.textContent = payload;
    if (ws && ws.readyState === WebSocket.OPEN) {
        try {
            ws.send(payload);
        } catch (_) {
            // ignore send issues
        }
    }
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

connectBtn?.addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        closeWebSocket();
        return;
    }

    const targetIp = (espIpInput?.value || '').trim();
    if (!targetIp) {
        alert('Please enter the target ESP32 IP address.');
        return;
    }

    setConnecting();

    try {
        ws = new WebSocket(`ws://${targetIp}/ws`);
    } catch (error) {
        ws = null;
        setDisconnected();
        alert('Connection Failure: Target ESP32 Device Not Available on Local Network.');
        return;
    }

    connectTimer = setTimeout(() => {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            closeWebSocket();
            alert('Connection Failure: Target ESP32 Device Not Available on Local Network.');
        }
    }, CONNECT_TIMEOUT_MS);

    ws.addEventListener('open', () => {
        if (connectTimer) {
            clearTimeout(connectTimer);
            connectTimer = null;
        }
        setConnected();
    });

    ws.addEventListener('close', () => {
        closeWebSocket();
    });

    ws.addEventListener('error', () => {
        // close event will finish cleanup, but keep UI honest immediately
        setDisconnected();
    });
});

// Device selection modal
laptopBtn?.addEventListener('click', () => {
    deviceModal.classList.add('hidden');
    switchToMode('laptop');
});

mobileBtn?.addEventListener('click', () => {
    deviceModal.classList.add('hidden');
    switchToMode('mobile');
});

switchBtn?.addEventListener('click', () => {
    switchToMode(currentMode === 'laptop' ? 'mobile' : 'laptop');
});

function switchToMode(mode) {
    currentMode = mode;
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
}

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
