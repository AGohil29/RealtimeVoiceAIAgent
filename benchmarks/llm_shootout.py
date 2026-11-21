"""Time to first token for a few models through the same OpenRouter key.

    python benchmarks/llm_shootout.py

Runs each model 3 times with a short prompt and prints the first-token latency of each run.
The voice agent only cares about the first token: everything after that streams while TTS
is already speaking.
"""
import asyncio
import json
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
MODELS = [
    ("anthropic/claude-haiku-4.5", None),
    ("openai/gpt-4.1-mini", None),
    ("google/gemini-2.5-flash-lite", None),
    ("meta-llama/llama-3.3-70b-instruct", None),       # whichever GPU host OpenRouter picks
    ("meta-llama/llama-3.3-70b-instruct", ["groq"]),   # same model, custom inference chips
    ("openai/gpt-oss-120b", ["groq"]),
]
PROMPT = [{"role": "user", "content": "Say hello in one short sentence."}]


async def first_token_ms(client, model, providers):
    body = {"model": model, "messages": PROMPT, "max_tokens": 40, "stream": True}
    if providers:
        body["provider"] = {"order": providers, "allow_fallbacks": True}
    t0 = time.perf_counter()
    async with client.stream("POST", URL, headers=HEADERS, json=body) as r:
        async for line in r.aiter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                if json.loads(line[6:])["choices"][0]["delta"].get("content"):
                    return round((time.perf_counter() - t0) * 1000)


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        for model, providers in MODELS:
            runs = [await first_token_ms(client, model, providers) for _ in range(3)]
            print(f"{model:40s} {str(providers or 'auto'):12s} {runs} ms")


asyncio.run(main())
