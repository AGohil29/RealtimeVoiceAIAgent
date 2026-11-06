import time

from pysilero_vad import SileroVoiceActivityDetector

SPEECH_THRESHOLD = 0.5   # probability above this counts as speech
SILENCE_MS = 700         # silence after which the VAD considers this stretch of speech over
CHUNK_MS = 32            # Silero looks at 512 samples at a time = 32ms at 16kHz


class VAD:
    """Turns a stream of 20ms mic frames into two events: speech_start and speech_end."""

    def __init__(self):
        self.model = SileroVoiceActivityDetector()
        self.buffer = b""
        self.speaking = False
        self.silence_ms = 0  # silence seen since the last speech chunk
        self.last_speech_at = None  # wall clock of the last chunk that had speech

    def process(self, frame: bytes) -> str | None:
        self.buffer += frame
        event = None
        chunk_bytes = self.model.chunk_bytes()

        # our frames are 20ms, the model wants 32ms, so regroup
        while len(self.buffer) >= chunk_bytes:
            chunk, self.buffer = self.buffer[:chunk_bytes], self.buffer[chunk_bytes:]
            is_speech = self.model.process_chunk(chunk) > SPEECH_THRESHOLD

            if is_speech:
                self.silence_ms = 0
                self.last_speech_at = time.perf_counter()
                if not self.speaking:
                    self.speaking = True
                    event = "speech_start"
            elif self.speaking:
                self.silence_ms += CHUNK_MS
                if self.silence_ms >= SILENCE_MS:
                    self.speaking = False
                    event = "speech_end"
        return event

    def reset(self):
        self.model.reset()
        self.buffer = b""
        self.speaking = False
        self.silence_ms = 0
