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


class Session:
    """One browser connection: streams audio to STT while the user talks, then replies."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.messages = []   # conversation history for the LLM
        self.stt_ws = None
        self.finals = []     # final transcript pieces of the current utterance
        self.reader = None   # task that reads transcripts from Deepgram

    async def start_listening(self):
        """Called when the user presses the button. Opens STT before any audio arrives."""
        self.stt_ws = await stt.connect()
        self.finals = []
        self.reader = asyncio.create_task(self.read_transcripts())

    async def read_transcripts(self):
        """Collect final pieces and show the live transcript in the browser."""
        async for text, is_final in stt.transcripts(self.stt_ws):
            if is_final:
                self.finals.append(text)
            live = " ".join(self.finals if is_final else [*self.finals, text])
            await self.ws.send_json({"type": "transcript", "text": live, "final": is_final})

    async def on_audio(self, frame: bytes):
        """Every 20ms frame goes straight to Deepgram while the user is still speaking."""
        if self.stt_ws:
            await stt.send_audio(self.stt_ws, frame)

    async def end_of_speech(self):
        """Called when the user releases the button. Most of the transcript is already done."""
        trace = Trace()

        await stt.finish(self.stt_ws)
        await self.reader  # returns once Deepgram has sent the last final and closed
        self.stt_ws = None
        transcript = " ".join(self.finals)
        trace.mark("stt_done")
        if not transcript:
            await self.ws.send_json({"type": "error", "message": "No speech detected"})
            return
        self.messages.append({"role": "user", "content": transcript})

        await self.ws.send_json({"type": "audio_start", "sample_rate": tts.SAMPLE_RATE})
        tts_ws = await tts.connect()
        forward = asyncio.create_task(forward_audio(tts_ws, self.ws, trace))

        reply = ""
        async for sentence in sentences(llm.chat_stream(self.messages), trace):
            if not reply:
                trace.mark("llm_first_sentence")
            reply += sentence + " "
            await tts.speak(tts_ws, sentence)  # TTS starts on this sentence while LLM writes the next
        trace.mark("llm_done")

        await tts.close(tts_ws)
        await forward  # ends when Deepgram has sent the last chunk and closed the socket
        self.messages.append({"role": "assistant", "content": reply.strip()})
        trace.save()

        await self.ws.send_json({
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
