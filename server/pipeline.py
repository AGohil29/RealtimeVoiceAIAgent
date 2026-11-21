import asyncio
import re
import time

from fastapi import WebSocket

from . import llm, stt, tts
from .trace import Trace
from .vad import VAD

SENTENCE_END = re.compile(r"[.!?]\s")
BARGE_IN_MIN_MS = 300  # the user must speak this long over the agent before we react
BACKCHANNELS = {"okay", "ok", "yeah", "yes", "yep", "right", "sure", "alright", "hmm", "hm", "hum", "mhm",
                "mhmm", "mmhmm", "mm", "uh", "huh", "uhhuh", "um", "ah", "oh", "got", "it", "i", "see", "cool",
                "nice", "great", "true"}
STOP_WORDS = {"stop", "wait", "pause", "enough", "shh"}  # "wait, wait": the user wants quiet, nothing to answer
MS_PER_BYTE = 1 / 48  # TTS audio is 24kHz, 16-bit: 48 bytes per millisecond
MS_PER_WORD = 300     # Aura speaks about three words a second (measured)
GREETING = "Hi! I am your voice assistant. What would you like to know?"
greeting_audio = None  # rendered once at startup, then reused for every session


async def prepare():
    global greeting_audio
    greeting_audio = await tts.synthesize(GREETING)


def real_words(text: str) -> set[str]:
    """The different words that are not noises of agreement ("okay", "mm-hmm"), so "wait, wait" is one word.
    Single letters are half-heard, skip them."""
    words = re.findall(r"[a-z']+", text.lower().replace("-", ""))
    return {w for w in words if w not in BACKCHANNELS and len(w) > 1}


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


async def forward_audio(tts_ws, ws: WebSocket, trace: Trace, sentence_ends: list):
    """Copy TTS audio to the browser as it arrives, and note where each sentence ends (in ms)."""
    audio_ms = 0
    async for kind, payload in tts.messages(tts_ws):
        if kind == "audio":
            if "tts_first_byte" not in trace.marks:
                trace.mark("tts_first_byte")
            audio_ms += len(payload) * MS_PER_BYTE
            await ws.send_bytes(payload)
        else:
            sentence_ends.append(audio_ms)
    trace.mark("audio_sent")


async def chain(first, rest):
    """A stream that starts with one piece we already have, then continues with the rest."""
    try:
        yield await first
    except StopAsyncIteration:
        return  # the model sent nothing at all: an empty reply, not a crash
    async for piece in rest:
        yield piece


class Session:
    """One browser connection. States: listening -> user_speaking -> agent_turn -> listening."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.messages = []   # conversation history for the LLM
        self.vad = VAD()     # only used to know when the last speech chunk was, for measuring
        self.state = "listening"
        self.stt_ws = None
        self.chunk = b""     # frames collected until we have 80ms for Flux
        self.reader = None   # task that reads turn events from Deepgram
        self.turn = None     # task running the current agent turn
        self.next_tts = None # a TTS connection opened ahead of time for the next reply
        self.speculation = None  # an LLM request started on EagerEndOfTurn, before the turn is confirmed
        self.paused = False  # agent audio paused because the user started talking
        self.user_talking = False  # Flux has a user turn open (it may have started while the agent spoke)
        self.over_agent = False    # that turn started while the agent had the turn
        self.heard = set()         # real words Flux heard in that turn, while the agent had the turn
        self.played = None         # after clear_audio: the browser's answer, how many ms of the reply it played
        self.sentences = []  # sentences of the current reply, in the order sent to TTS
        self.sentence_ends = []  # audio position (ms) where each of those sentences ends

    async def start(self):
        """Greet from cached audio, and use that time to open every connection we will need."""
        self.state = "agent_turn"
        self.sentences, self.sentence_ends = [GREETING], [len(greeting_audio) * MS_PER_BYTE]
        self.messages.append({"role": "assistant", "content": GREETING})
        await self.ws.send_json({"type": "audio_start", "sample_rate": tts.SAMPLE_RATE})
        await self.ws.send_bytes(greeting_audio)
        await self.ws.send_json({"type": "turn_done", "greeting": True})

        # the user is listening to the greeting: pay the connection costs now, not on the first turn
        self.stt_ws = await stt.connect()
        self.reader = asyncio.create_task(self.read_events())
        self.next_tts = asyncio.create_task(tts.connect())
        asyncio.create_task(llm.warm_up())

    async def tts_connection(self):
        """Take the pre-opened TTS connection and immediately open another one for the next turn."""
        tts_ws = await self.next_tts
        self.next_tts = asyncio.create_task(tts.connect())
        if tts_ws.close_code is not None:  # Deepgram closed it while we were idle, open a fresh one
            tts_ws = await tts.connect()
        return tts_ws

    async def on_audio(self, frame: bytes):
        """Every 20ms frame goes to Flux, in all states. Flux needs the silence too."""
        event = self.vad.process(frame)
        self.chunk += frame
        if len(self.chunk) >= len(frame) * stt.CHUNK_FRAMES:
            await stt.send_audio(self.stt_ws, self.chunk)
            self.chunk = b""

        # barge-in, stage 1: the user has been talking over the agent for 300ms. Pause, instantly.
        if self.state == "agent_turn":
            if not self.paused and self.vad.speaking and self.vad.speech_ms >= BARGE_IN_MIN_MS:
                self.paused = True
                await self.ws.send_json({"type": "pause_audio", "after_ms": self.vad.speech_ms})
            elif self.paused and event == "speech_end" and not self.heard:
                await self.resume()  # they stopped and Flux heard no real word: a cough, a noise, "okay"

    async def read_events(self):
        """Turn events from Flux drive the state machine."""
        async for event, transcript in stt.events(self.stt_ws):
            if event == "StartOfTurn":
                self.user_talking, self.over_agent, self.heard = True, self.state == "agent_turn", set()
            elif event == "EndOfTurn":
                self.user_talking = False

            if self.state == "listening" and event == "StartOfTurn":
                self.state = "user_speaking"
                await self.ws.send_json({"type": "speech_start"})

            # barge-in, stage 2: Flux heard words while the agent had the turn. Real interruption or not?
            # Early guesses change ("A" becomes "Okay"), so wait for two different real words, or one in the final text.
            if self.state == "agent_turn" and transcript:
                real = self.heard = real_words(transcript)
                if len(real) >= 2 or (real and event == "EndOfTurn"):
                    await self.interrupt()
                elif event == "EndOfTurn":
                    await self.resume()  # just "okay" or "mm-hmm", carry on

            if self.state != "user_speaking":
                continue

            await self.ws.send_json({"type": "transcript", "text": transcript, "final": event == "EndOfTurn"})
            if event == "EagerEndOfTurn" and transcript:
                self.speculate(transcript)
            elif event == "TurnResumed":
                self.drop_speculation()
            elif event == "EndOfTurn" and transcript:
                real = real_words(transcript)
                if (self.over_agent and not real) or (real and real <= STOP_WORDS):
                    self.drop_speculation()
                    self.state = "listening"  # "okay" over the agent, or just "wait" / "stop": stop and listen, nothing to answer
                    continue
                await self.end_of_turn(transcript)  # anything else is answered, even one word ("Yes please", "Mars?")

    def speculate(self, transcript: str):
        """Flux thinks the user is probably done. Start the LLM now, in case it is right."""
        self.drop_speculation()
        stream = llm.chat_stream([*self.messages, {"role": "user", "content": transcript}])
        self.speculation = (transcript, stream, asyncio.create_task(anext(stream)))

    def drop_speculation(self):
        if self.speculation:
            self.speculation[2].cancel()
            self.speculation = None

    def take_speculation(self, transcript: str):
        """If the confirmed transcript matches the guess, use the reply already in flight."""
        if not self.speculation or self.speculation[0] != transcript:
            self.drop_speculation()
            return None
        _, stream, first = self.speculation
        self.speculation = None
        return chain(first, stream)

    async def resume(self):
        if self.paused:
            self.paused = False
            await self.ws.send_json({"type": "resume_audio"})

    async def interrupt(self):
        """Stop everything the agent is doing and hand the turn to the user."""
        if self.turn:
            self.turn.cancel()
        self.paused = False
        self.state = "user_speaking"
        self.played = asyncio.get_running_loop().create_future()
        await self.ws.send_json({"type": "clear_audio"})  # browser replies with how much it played
        self.keep_heard(await self.played)  # fix the history now, before the user's next turn can start

    async def on_played(self, played_ms: float):
        self.played.set_result(played_ms)

    def keep_heard(self, played_ms: float):
        """After an interruption: keep only the part of the reply the user actually heard."""
        if self.messages[-1]["role"] == "assistant":
            self.messages.pop()  # the reply was already saved in full, replace it with what was heard
        heard = [s for s, end in zip(self.sentences, self.sentence_ends) if end <= played_ms]
        if len(heard) < len(self.sentences):
            # the sentence that was cut: keep the words in proportion to how much of it played
            start = self.sentence_ends[len(heard) - 1] if heard else 0
            words = self.sentences[len(heard)].split()
            if len(self.sentence_ends) > len(heard):
                span = self.sentence_ends[len(heard)] - start
            else:
                span = len(words) * MS_PER_WORD  # Deepgram has not finished rendering it yet: estimate its length
            fraction = min(1, (played_ms - start) / span) if span else 0
            partial = " ".join(words[: round(len(words) * fraction)])
            if partial:
                heard.append(partial + "...")
        if heard:
            self.messages.append({"role": "assistant", "content": " ".join(heard)})

    async def end_of_turn(self, transcript: str):
        """Flux is confident the user is done. The transcript is final, no waiting."""
        self.state = "agent_turn"
        turn_detection_ms = round((time.perf_counter() - self.vad.last_speech_at) * 1000)
        self.vad.reset()  # so that only speech that starts from now on counts as talking over the agent
        self.paused, self.heard = False, set()  # a new reply starts fresh: not paused, nothing heard over it yet
        await self.ws.send_json({"type": "speech_end", "turn_detection_ms": turn_detection_ms})
        self.turn = asyncio.create_task(self.run_turn(transcript, turn_detection_ms))  # frames keep flowing

    async def playback_done(self):
        """The browser finished playing the reply. Back to listening, or to the user if they already started."""
        self.vad.reset()
        self.state = "user_speaking" if self.user_talking else "listening"

    async def run_turn(self, transcript: str, turn_detection_ms: int):
        """Runs after the end of turn. The transcript is complete already."""
        trace = Trace()
        trace.mark("stt_done")  # nothing to wait for any more, Flux gave us the final text with the decision
        self.messages.append({"role": "user", "content": transcript})

        await self.ws.send_json({"type": "audio_start", "sample_rate": tts.SAMPLE_RATE})
        self.sentences, self.sentence_ends = [], []
        tts_ws = await self.tts_connection()
        forward = asyncio.create_task(forward_audio(tts_ws, self.ws, trace, self.sentence_ends))

        stream = self.take_speculation(transcript)
        speculated = stream is not None
        if not speculated:
            stream = llm.chat_stream(self.messages)
        try:
            async for sentence in sentences(stream, trace):
                if not self.sentences:
                    trace.mark("llm_first_sentence")
                self.sentences.append(sentence)
                await tts.speak(tts_ws, sentence)  # TTS starts on this sentence while LLM writes the next
            trace.mark("llm_done")

            await tts.close(tts_ws)
            await forward  # ends when Deepgram has sent the last chunk and closed the socket
        except asyncio.CancelledError:
            forward.cancel()      # interrupted: stop forwarding audio
            await tts_ws.close()  # and stop Deepgram rendering
            return                # interrupt() keeps what was heard
        reply = " ".join(self.sentences)
        self.messages.append({"role": "assistant", "content": reply})
        trace.marks["turn_detection"] = turn_detection_ms
        trace.marks["first_audio"] = turn_detection_ms + trace.marks["tts_first_byte"]  # from the real end of speech
        trace.save()

        await self.ws.send_json({
            "type": "turn_done",
            "transcript": transcript,
            "reply": reply,
            "provider": llm.last_provider,
            "speculated": speculated,
            "timings": {
                "turn_detection": turn_detection_ms,
                "stt": trace.marks["stt_done"],
                "llm_first_token": trace.duration("stt_done", "llm_first_token"),
                "llm_first_sentence": trace.duration("llm_first_token", "llm_first_sentence"),
                "tts_first_byte": trace.duration("llm_first_sentence", "tts_first_byte"),
                "first_audio": turn_detection_ms + trace.marks["tts_first_byte"],
                "total": turn_detection_ms + trace.marks["audio_sent"],
            },
        })
