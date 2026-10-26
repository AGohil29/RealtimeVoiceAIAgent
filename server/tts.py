import json
import os

import websockets

DEEPGRAM_URL = "wss://api.deepgram.com/v1/speak"
SAMPLE_RATE = 24000


async def connect():
    """Open a streaming TTS connection. Audio comes back as PCM16, 24kHz, mono."""
    url = f"{DEEPGRAM_URL}?model=aura-2-thalia-en&encoding=linear16&sample_rate={SAMPLE_RATE}"
    headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
    return await websockets.connect(url, additional_headers=headers)


async def speak(tts_ws, text: str):
    """Queue a piece of text and ask Deepgram to start rendering it right away."""
    await tts_ws.send(json.dumps({"type": "Speak", "text": text}))
    await tts_ws.send(json.dumps({"type": "Flush"}))


async def close(tts_ws):
    """Tell Deepgram we are done. It renders anything left, then closes the socket."""
    await tts_ws.send(json.dumps({"type": "Close"}))


async def audio_chunks(tts_ws):
    """Yield audio bytes as they arrive. JSON status messages are skipped."""
    async for msg in tts_ws:
        if isinstance(msg, bytes):
            yield msg
