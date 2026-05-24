import socket
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from server.core.csi_processor import CSIProcessor

# Configuration
UDP_IP = "127.0.0.1"
UDP_PORT = 5000
NUM_SUBCARRIERS = 64

# Initialize Network and Math Core
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
sock.setblocking(False)  # Prevent script from freezing when waiting for packets
processor = CSIProcessor(num_subcarriers=NUM_SUBCARRIERS)

# Set up the Matplotlib Plotting Figure
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(6, 6))
ax.set_xlim(-3, 3)
ax.set_ylim(-3, 3)
ax.set_title("Project 180: Live Wi-Fi CSI Tracking Feed", color='#00FF00', fontsize=12)
ax.grid(True, color='#222222', linestyle='--')

# Draw radar target marker and path trail
target_dot, = ax.plot([], [], 'go', ms=10, label="Tracked Target")
trail_line, = ax.plot([], [], 'g-', alpha=0.3)

# Store recent positions to show movement history/trail
x_history, y_history = [], []

def update(frame):
    global x_history, y_history
    try:
        # Read the latest packet from the network queue
        data, addr = sock.recvfrom(4096)
        payload = json.loads(data.decode('utf-8'))
        raw_amp = np.array(payload.get('amplitude') or payload.get('csi') or [], dtype=float)
        raw_phase = np.array(payload.get('phase') or np.zeros_like(raw_amp), dtype=float)

        # Normalize arrays
        if raw_amp.size != NUM_SUBCARRIERS:
            raw_amp = np.resize(raw_amp, NUM_SUBCARRIERS)
        if raw_phase.size != NUM_SUBCARRIERS:
            raw_phase = np.resize(raw_phase, NUM_SUBCARRIERS)

        # Process metrics through your math pipeline
        coordinates = processor.process_frame(raw_amp, raw_phase)

        if coordinates:
            x, y = coordinates['x'], coordinates['y']

            # Maintain trailing history (last 15 frames)
            x_history.append(x)
            y_history.append(y)
            if len(x_history) > 15:
                x_history.pop(0)
                y_history.pop(0)

            # Update visual elements
            target_dot.set_data([x], [y])
            trail_line.set_data(x_history, y_history)

            # Flash status info to terminal
            print(f"Visualizing target at -> X: {x}m, Y: {y}m")

    except BlockingIOError:
        # No data packet in buffer right now, skip frame update smoothly
        pass
    except Exception:
        # Ignore malformed packets
        pass

    return target_dot, trail_line


if __name__ == '__main__':
    # Animate the canvas at a low interval to match simulation speed
    ani = FuncAnimation(fig, update, interval=30, blit=True, cache_frame_data=False)
    plt.legend(loc="upper right")
    plt.show()

    sock.close()
