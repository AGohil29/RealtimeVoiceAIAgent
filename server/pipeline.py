from fastapi import WebSocket

from . import llm, stt, tts
from .trace import Trace


async def run_turn(ws: WebSocket, pcm: bytes, messages: list[dict]):
    """One full turn: audio in -> STT -> LLM -> TTS -> audio out. Each step waits for the previous."""
    trace = Trace()

    transcript = await stt.transcribe(pcm)
    trace.mark("stt_done")
    if not transcript:
        await ws.send_json({"type": "error", "message": "No speech detected"})
        return

    messages.append({"role": "user", "content": transcript})
    reply = await llm.chat(messages)
    messages.append({"role": "assistant", "content": reply})
    trace.mark("llm_done")

    audio = await tts.synthesize(reply)
    trace.mark("tts_done")

    await ws.send_json({"type": "audio_start", "sample_rate": tts.SAMPLE_RATE})
    await ws.send_bytes(audio)
    trace.mark("audio_sent")
    trace.save()

    await ws.send_json({
        "type": "turn_done",
        "transcript": transcript,
        "reply": reply,
        "timings": {
            "stt": trace.marks["stt_done"],
            "llm": trace.duration("stt_done", "llm_done"),
            "tts": trace.duration("llm_done", "tts_done"),
            "total": trace.marks["audio_sent"],
        },
    })
