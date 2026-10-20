import json

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

load_dotenv()

from .pipeline import run_turn  # noqa: E402  (needs env vars loaded first)

app = FastAPI()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    audio = bytearray()   # frames collected while the user holds the button
    messages = []         # conversation history for the LLM

    while True:
        msg = await ws.receive()
        if msg["type"] == "websocket.disconnect":
            break

        if msg.get("bytes") is not None:
            audio += msg["bytes"]
            continue

        data = json.loads(msg["text"])
        if data["type"] == "ping":
            await ws.send_json({"type": "pong", "t": data["t"]})
        elif data["type"] == "start":
            audio.clear()
        elif data["type"] == "end_of_speech":
            await run_turn(ws, bytes(audio), messages)


app.mount("/", StaticFiles(directory="web", html=True), name="web")
