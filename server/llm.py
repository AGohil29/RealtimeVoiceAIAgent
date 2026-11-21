import json
import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Chosen for time to first token, measure with benchmarks/llm_shootout.py. Any OpenRouter model id works here.
MODEL = os.environ.get("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")
# Which host OpenRouter should send it to. Groq runs Llama on custom chips: ~140ms to the first
# token, versus ~1000ms on the GPU hosts OpenRouter picks by default. Empty = let OpenRouter pick.
PROVIDERS = [p for p in os.environ.get("LLM_PROVIDERS", "groq").split(",") if p]

# One client for the whole process: the TLS connection to OpenRouter is set up once and reused,
# instead of a fresh handshake (a few hundred ms from far away) on every turn.
client = httpx.AsyncClient(timeout=60)
last_provider = None  # which host served the last request, so the UI can show it


async def warm_up():
    """Make one tiny real request so the connection and the route to the model are ready."""
    async for _ in chat_stream([{"role": "user", "content": "Hi"}], max_tokens=1):
        pass

SYSTEM_PROMPT = """You are a friendly voice assistant. Your reply will be spoken aloud.
Keep answers short, one or two sentences. Use plain spoken language.
No markdown, no lists, no emojis. Say numbers in words, like "forty five dollars"."""


async def chat_stream(messages: list[dict], max_tokens: int = 150):
    """Send the conversation so far and yield the reply one piece of text at a time."""
    global last_provider
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "max_tokens": max_tokens,
        "stream": True,
    }
    if PROVIDERS:
        body["provider"] = {"order": PROVIDERS, "allow_fallbacks": True}
    async with client.stream("POST", OPENROUTER_URL, headers=headers, json=body) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            # server-sent events: each line is "data: {...}", the last one is "data: [DONE]"
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            data = json.loads(line[6:])
            last_provider = data.get("provider", last_provider)
            delta = data["choices"][0]["delta"]
            if delta.get("content"):
                yield delta["content"]
