import asyncio
import json
import random
import time
from aiohttp import web
import socket

UDP_IP = "127.0.0.1"
UDP_PORT = 5000
FPS = 25

async def udp_broadcaster(loop):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frame = 0
    try:
        while True:
            payload = {
                "frame_id": frame,
                "ts": time.time(),
                "csi": [round(random.uniform(-1.0, 1.0), 6) for _ in range(64)],
            }
            data = json.dumps(payload).encode('utf-8')
            sock.sendto(data, (UDP_IP, UDP_PORT))
            frame += 1
            await asyncio.sleep(1.0 / FPS)
    finally:
        sock.close()

async def handle_index(request):
    return web.FileResponse('static/index.html')

async def handle_status(request):
    return web.json_response({"status": "running", "fps": FPS})

async def start_background_tasks(app):
    app['broadcaster'] = asyncio.create_task(udp_broadcaster(asyncio.get_event_loop()))

async def cleanup_background_tasks(app):
    app['broadcaster'].cancel()
    await app['broadcaster']

def main():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/status', handle_status)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    web.run_app(app, host='0.0.0.0', port=3000)

if __name__ == '__main__':
    main()
