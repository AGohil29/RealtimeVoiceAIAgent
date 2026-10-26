import json
import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-haiku-4.5")

SYSTEM_PROMPT = """You are a friendly voice assistant. Your reply will be spoken aloud.
Keep answers short, one or two sentences. Use plain spoken language.
No markdown, no lists, no emojis. Say numbers in words, like "forty five dollars"."""


async def chat_stream(messages: list[dict]):
    """Send the conversation so far and yield the reply one piece of text at a time."""
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "max_tokens": 150,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", OPENROUTER_URL, headers=headers, json=body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                # server-sent events: each line is "data: {...}", the last one is "data: [DONE]"
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                delta = json.loads(line[6:])["choices"][0]["delta"]
                if delta.get("content"):
                    yield delta["content"]
