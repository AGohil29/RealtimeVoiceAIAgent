import json
import os

import websockets

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"


async def connect():
    """Open a live transcription connection. We send PCM16 16kHz frames, it sends transcripts."""
    params = "model=nova-3&encoding=linear16&sample_rate=16000&channels=1&interim_results=true&smart_format=true"
    headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
    return await websockets.connect(f"{DEEPGRAM_URL}?{params}", additional_headers=headers)


async def send_audio(stt_ws, frame: bytes):
    await stt_ws.send(frame)


async def finish(stt_ws):
    """No more audio. Deepgram sends the last final transcript, then closes the socket."""
    await stt_ws.send(json.dumps({"type": "CloseStream"}))


async def transcripts(stt_ws):
    """Yield (text, is_final) as Deepgram sends results.

    Interim results (is_final False) are guesses that can still change.
    Final results (is_final True) are fixed and will not change any more.
    """
    async for msg in stt_ws:
        data = json.loads(msg)
        if data["type"] != "Results":
            continue  # Metadata and other housekeeping messages
        text = data["channel"]["alternatives"][0]["transcript"]
        if text:
            yield text, data["is_final"]
