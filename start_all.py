#!/usr/bin/env python3
"""
Start simulator, server, and visualizer from a single terminal and print LAN URLs.
Run this from the project root while your venv is active:

    python start_all.py

Press Ctrl-C to stop all services.
"""
import sys
import socket
import subprocess
import threading
import os
import signal
import time


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't actually send data
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def stream_proc_output(name, proc):
    try:
        for line in proc.stdout:
            print(f"[{name}] {line.rstrip()}")
    except Exception:
        pass


def start_process(name, cmd, cwd=None):
    env = os.environ.copy()
    # Force unbuffered python output
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env, cwd=cwd)
    t = threading.Thread(target=stream_proc_output, args=(name, proc), daemon=True)
    t.start()
    return proc


def main():
    ip = get_local_ip()
    print(f"Detected host IP: {ip}")
    print("URLs to open in browser:")
    print(f"- Simulator UI: http://{ip}:3000")
    print(f"- App (Flask): http://{ip}:8787")
    print("")

    python = sys.executable

    # Commands to run
    cmds = [
        ("simulator", [python, "server/simulator/sim.py"]),
        ("app", [python, "-m", "server.app"]),
        ("visualizer", [python, "-m", "server.core.radar_visualizer"]),
    ]

    procs = []
    try:
        for name, cmd in cmds:
            print(f"Starting {name}: {' '.join(cmd)}")
            proc = start_process(name, cmd)
            procs.append((name, proc))

        # Wait until Ctrl-C (cross-platform)
        try:
            while True:
                alive = any(p.poll() is None for _, p in procs)
                if not alive:
                    print("All child processes exited.")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    except KeyboardInterrupt:
        pass
    finally:
        print("Shutting down child processes...")
        for name, p in procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
