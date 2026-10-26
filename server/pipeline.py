import asyncio
import re

from fastapi import WebSocket

from . import llm, stt, tts
from .trace import Trace

SENTENCE_END = re.compile(r"[.!?]\s")


async def sentences(text_stream, trace: Trace):
    """Group streamed text pieces into whole sentences, so TTS gets natural chunks."""
    buffer = ""
    async for piece in text_stream:
        if "llm_first_token" not in trace.marks:
            trace.mark("llm_first_token")
        buffer += piece
        while match := SENTENCE_END.search(buffer):
            yield buffer[: match.end()].strip()
            buffer = buffer[match.end():]
    if buffer.strip():
        yield buffer.strip()


async def forward_audio(tts_ws, ws: WebSocket, trace: Trace):
    """Copy TTS audio to the browser as soon as each chunk arrives."""
    async for chunk in tts.audio_chunks(tts_ws):
        if "tts_first_byte" not in trace.marks:
            trace.mark("tts_first_byte")
        await ws.send_bytes(chunk)
    trace.mark("audio_sent")


async def run_turn(ws: WebSocket, pcm: bytes, messages: list[dict]):
    """One turn: STT, then LLM and TTS run at the same time, sentence by sentence."""
    trace = Trace()

    transcript = await stt.transcribe(pcm)
    trace.mark("stt_done")
    if not transcript:
        await ws.send_json({"type": "error", "message": "No speech detected"})
        return
    messages.append({"role": "user", "content": transcript})

    await ws.send_json({"type": "audio_start", "sample_rate": tts.SAMPLE_RATE})
    tts_ws = await tts.connect()
    forward = asyncio.create_task(forward_audio(tts_ws, ws, trace))

    reply = ""
    async for sentence in sentences(llm.chat_stream(messages), trace):
        if not reply:
            trace.mark("llm_first_sentence")
        reply += sentence + " "
        await tts.speak(tts_ws, sentence)  # TTS starts on this sentence while LLM writes the next
    trace.mark("llm_done")

    await tts.close(tts_ws)
    await forward  # ends when Deepgram has sent the last chunk and closed the socket
    messages.append({"role": "assistant", "content": reply.strip()})
    trace.save()

    await ws.send_json({
        "type": "turn_done",
        "transcript": transcript,
        "reply": reply.strip(),
        "timings": {
            "stt": trace.marks["stt_done"],
            "llm_first_token": trace.duration("stt_done", "llm_first_token"),
            "llm_first_sentence": trace.duration("llm_first_token", "llm_first_sentence"),
            "tts_first_byte": trace.duration("llm_first_sentence", "tts_first_byte"),
            "first_audio": trace.marks["tts_first_byte"],
            "total": trace.marks["audio_sent"],
        },
    })
