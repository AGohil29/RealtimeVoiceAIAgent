# Project Changes

## Phase 0: Audio Transport

- Added a browser client that captures microphone audio as mono, 16 kHz PCM16 and sends 20 ms frames over a WebSocket.
- Added a FastAPI server to serve the client, accept audio frames, and report transport statistics.

## Phase 1: Batch Voice Pipeline

- Added push-to-talk: the browser sends audio while the talk button is held, and the server processes the collected recording when speech ends.
- Added a sequential speech-to-text, language-model, and text-to-speech pipeline. The full recording is transcribed by Deepgram, conversation history is sent to OpenRouter, and Deepgram synthesizes the reply.
- Added `server/stt.py`, `server/llm.py`, and `server/tts.py` for provider requests; `server/pipeline.py` coordinates a turn, and `server/main.py` handles WebSocket messages.
- Added browser playback for returned PCM audio in `web/playback.js` and a turn history table displaying the transcript, response, and timings.
- Added `server/trace.py` to record pipeline timings in `traces.jsonl`. The interface reports STT, LLM, TTS, total server time, and voice-to-voice time.
- Added `benchmarks/simulate.py` to generate spoken test input and exercise the button protocol without a microphone; `--button` selects the current push-to-talk flow.
- Added `httpx` to `requirements.txt` for asynchronous requests to the speech and language-model APIs.

## Phase 2: Streaming LLM and TTS

- Updated the OpenRouter client to stream response text as it is generated.
- Split the streamed response into sentences and send each sentence to Deepgram's streaming TTS connection while the LLM generates the next.
- Forwarded TTS audio chunks to the browser as they arrive, and scheduled playback back-to-back to avoid gaps between chunks.
- Updated the interface to identify the streaming phase and show timing to the first LLM token, first sentence, and first audio byte, alongside total server time and voice-to-voice latency.
- Added `websockets` to `requirements.txt` for the streaming Deepgram TTS connection.

## Configuration

Set `DEEPGRAM_API_KEY` and `OPENROUTER_API_KEY` in a local `.env` file. Copy `.env.example` as a starting point; do not commit `.env`.

Phase 1 processes each recording in batches: transcription, language-model response, and speech synthesis run in sequence before reply audio is sent. Phase 2 keeps transcription as a batch step, then streams the LLM response and TTS audio to reduce time to first audio.