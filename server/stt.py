import os

import httpx

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


async def transcribe(pcm: bytes) -> str:
    """Send a whole audio clip (PCM16, 16kHz, mono) and get the transcript back."""
    params = {
        "model": "nova-3",
        "encoding": "linear16",
        "sample_rate": 16000,
        "smart_format": "true",
    }
    headers = {
        "Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}",
        "Content-Type": "application/octet-stream",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(DEEPGRAM_URL, params=params, headers=headers, content=pcm)
        r.raise_for_status()

    return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
