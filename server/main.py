import asyncio
import json
import time

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI()

# 16kHz, 16-bit mono, 20ms per frame -> 320 samples -> 640 bytes
SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    frames = 0
    bytes_total = 0
    last_report = time.perf_counter()

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"] is not None:
                # one 20ms PCM16 audio frame from the browser
                frames += 1
                bytes_total += len(msg["bytes"])

            elif "text" in msg and msg["text"] is not None:
                data = json.loads(msg["text"])
                if data["type"] == "ping":
                    # send the client's timestamp back so it can compute round-trip time
                    await ws.send_json({"type": "pong", "t": data["t"]})

            # once a second, tell the browser how much audio reached the server
            now = time.perf_counter()
            if now - last_report >= 1.0:
                elapsed = now - last_report
                await ws.send_json({
                    "type": "stats",
                    "frames_per_sec": round(frames / elapsed),
                    "bytes_per_sec": round(bytes_total / elapsed),
                    "frame_bytes": FRAME_BYTES,
                })
                frames = 0
                bytes_total = 0
                last_report = now

    except WebSocketDisconnect:
        pass


# serve the browser client from web/
app.mount("/", StaticFiles(directory="web", html=True), name="web")
