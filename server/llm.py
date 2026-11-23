import json
import os
from dataclasses import dataclass

import httpx

from . import tools

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
No markdown, no lists, no emojis. Say numbers in words, like "forty five dollars".
Use the tools to look things up instead of guessing. Before cancelling an order, say back the
order id and ask the user to confirm, and call cancel_order only after they say yes.
If a tool returns an error, say sorry in plain words and offer what you can do instead.
Never read out error codes or technical details."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""  # JSON, arrives in pieces while streaming

    def as_message(self):
        return {"id": self.id, "type": "function", "function": {"name": self.name, "arguments": self.arguments}}


async def chat_stream(messages: list[dict], max_tokens: int = 150):
    """Send the conversation so far and yield the reply one piece of text at a time.

    If the model decides to call tools instead, the ToolCall objects are yielded at the end.
    """
    global last_provider
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "max_tokens": max_tokens,
        "stream": True,
        "tools": tools.DEFINITIONS,
    }
    calls = {}  # index -> ToolCall, because a call's arguments arrive in several chunks
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
            if not data.get("choices"):
                continue  # keep-alive or usage chunk, no content
            delta = data["choices"][0]["delta"]
            if delta.get("content"):
                yield delta["content"]
            for part in delta.get("tool_calls") or []:
                call = calls.setdefault(part["index"], ToolCall(part.get("id"), part["function"].get("name")))
                call.arguments += part["function"].get("arguments") or ""
    for call in calls.values():
        yield call
