import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-haiku-4.5")

SYSTEM_PROMPT = """You are a friendly voice assistant. Your reply will be spoken aloud.
Keep answers short, one or two sentences. Use plain spoken language.
No markdown, no lists, no emojis. Say numbers in words, like "forty five dollars"."""


async def chat(messages: list[dict]) -> str:
    """Send the conversation so far and get the full reply text back."""
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "max_tokens": 150,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(OPENROUTER_URL, headers=headers, json=body)
        r.raise_for_status()

    return r.json()["choices"][0]["message"]["content"]
