import os

import httpx

DEEPGRAM_URL = "https://api.deepgram.com/v1/speak"
SAMPLE_RATE = 24000


async def synthesize(text: str) -> bytes:
    """Turn text into a whole audio clip (PCM16, 24kHz, mono)."""
    params = {
        "model": "aura-2-thalia-en",
        "encoding": "linear16",
        "sample_rate": SAMPLE_RATE,
        "container": "none",  # raw PCM, no WAV header
    }
    headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(DEEPGRAM_URL, params=params, headers=headers, json={"text": text})
        r.raise_for_status()

    return r.content
