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

## Configuration

Set `DEEPGRAM_API_KEY` and `OPENROUTER_API_KEY` in a local `.env` file. Copy `.env.example` as a starting point; do not commit `.env`.

This phase processes each recording in batches: transcription, language-model response, and speech synthesis run in sequence before reply audio is sent.