import json
import os

import websockets

# Flux is Deepgram's conversational model: it transcribes AND decides when the turn is over.
DEEPGRAM_URL = "wss://api.deepgram.com/v2/listen"
EOT_THRESHOLD = 0.7   # end the turn when the model is this confident the user is done
CHUNK_FRAMES = 4      # Flux works best with 80ms of audio at a time = 4 of our 20ms frames


async def connect():
    """One connection for the whole session. Audio flows in continuously, silence included."""
    params = f"model=flux-general-en&encoding=linear16&sample_rate=16000&eot_threshold={EOT_THRESHOLD}"
    headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
    return await websockets.connect(f"{DEEPGRAM_URL}?{params}", additional_headers=headers)


async def send_audio(stt_ws, chunk: bytes):
    await stt_ws.send(chunk)


async def events(stt_ws):
    """Yield (event, transcript) for every turn event Flux sends.

    StartOfTurn  the user started speaking
    Update       transcript so far, still changing
    EndOfTurn    the model is confident the user is done, transcript is final
    """
    async for msg in stt_ws:
        data = json.loads(msg)
        if data["type"] == "TurnInfo":
            yield data["event"], data["transcript"]
