import socket
import numpy as np
import json
from server.core.csi_processor import CSIProcessor

# Network Parameters
UDP_IP = "127.0.0.1"  # Localhost loopback for Docker simulator
UDP_PORT = 5000       # Target ingestion port
NUM_SUBCARRIERS = 64

# Initialize Core Processing Subsystems
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
processor = CSIProcessor(num_subcarriers=NUM_SUBCARRIERS)

print(f"📡 Real-Time Localized Radar Ingestion Pipeline Online.")
print(f"Listening on udp://{UDP_IP}:{UDP_PORT}... Press Ctrl+C to terminate.")

try:
    while True:
        # 1. Capture packet buffer stream
        data, addr = sock.recvfrom(8192)
        
        try:
            # Parse incoming telemetry strings (assuming JSON frame layout from sim)
            payload = json.loads(data.decode('utf-8'))
            
            # Support multiple frame layouts
            if 'amplitude' in payload and 'phase' in payload:
                raw_amp = np.array(payload['amplitude'], dtype=float)
                raw_phase = np.array(payload['phase'], dtype=float)
            elif 'csi' in payload:
                # simulator may send complex-like CSI values; treat as amplitude
                raw_amp = np.abs(np.array(payload['csi'], dtype=float))
                raw_phase = np.zeros_like(raw_amp)
            else:
                # fallback: try node -> amplitude/phase
                node = (payload.get('nodes') or [None])[0]
                if node and 'amplitude' in node:
                    raw_amp = np.array(node['amplitude'], dtype=float)
                    raw_phase = np.array(node.get('phase', np.zeros_like(raw_amp)), dtype=float)
                else:
                    raise ValueError('Unrecognized JSON frame format')

            # Normalize length: pad/truncate to NUM_SUBCARRIERS
            if raw_amp.size != NUM_SUBCARRIERS:
                raw_amp = np.resize(raw_amp, NUM_SUBCARRIERS)
            if raw_phase.size != NUM_SUBCARRIERS:
                raw_phase = np.resize(raw_phase, NUM_SUBCARRIERS)

            # 2. Feed the raw physical metrics through the signal conditioning filter
            coordinates = processor.process_frame(raw_amp, raw_phase)

            # 3. Output tracking coordinates if system calibration is complete
            if coordinates:
                print(f"🎯 Target Tracked -> X: {coordinates['x']}m | Y: {coordinates['y']}m | Z: {coordinates['z']}m")
                
        except (ValueError, KeyError, json.JSONDecodeError):
            # Fallback handling for raw packed binary array parsing if data is unformatted bytes
            if len(data) >= NUM_SUBCARRIERS * 2:
                raw_amp = np.frombuffer(data, dtype=np.uint8, count=NUM_SUBCARRIERS).astype(float)
                raw_phase = np.frombuffer(data, dtype=np.int8, offset=NUM_SUBCARRIERS, count=NUM_SUBCARRIERS).astype(float) * (np.pi / 128.0)
                
                coordinates = processor.process_frame(raw_amp, raw_phase)
                if coordinates:
                    print(f"🎯 Target Tracked -> X: {coordinates['x']}m | Y: {coordinates['y']}m | Z: {coordinates['z']}m")

except KeyboardInterrupt:
    print("\nShutting down spatial radar tracking loops safely.")
    sock.close()
