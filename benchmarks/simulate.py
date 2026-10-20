"""Simulated user for benchmarking without a microphone.

Generates the question as speech with Deepgram TTS (16kHz, like our mic), streams it to the
server one 20ms frame at a time, and prints every event with a timestamp.

    python benchmarks/simulate.py "What is the capital of India?"
    python benchmarks/simulate.py "I want to book a flight to ... Delhi"   # " ... " = a 1 second pause
    python benchmarks/simulate.py "Tell me about the moon." --interrupt "Wait, tell me about Mars instead."
    python benchmarks/simulate.py "Tell me about the moon." --interrupt "Okay."   # a backchannel, agent carries on
    python benchmarks/simulate.py "Cancel order 1234." --then "Yes, cancel it."    # a second turn after the reply
    python benchmarks/simulate.py --idle                                          # say nothing, watch the silence handling
    python benchmarks/simulate.py --button "..."   # phases 1 to 3 (hold-to-talk protocol)

Run the server first: uvicorn server.main:app
"""
import asyncio
import json
import os
import sys
import time

import httpx
import websockets
from dotenv import load_dotenv

load_dotenv()

BUTTON = "--button" in sys.argv
IDLE = "--idle" in sys.argv
INTERRUPT = sys.argv[sys.argv.index("--interrupt") + 1] if "--interrupt" in sys.argv else None
THEN = sys.argv[sys.argv.index("--then") + 1] if "--then" in sys.argv else None
QUESTION = next((a for a in sys.argv[1:] if not a.startswith("--") and a not in (INTERRUPT, THEN)), "What is the capital of India?")
SERVER = "ws://127.0.0.1:8000/ws"


def silence(ms):
    return bytes(32 * ms)  # 16kHz x 2 bytes = 32 bytes per ms


async def speech(text):
    params = {"model": "aura-2-thalia-en", "encoding": "linear16", "sample_rate": 16000, "container": "none"}
    headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.deepgram.com/v1/speak", params=params, headers=headers, json={"text": text})
        r.raise_for_status()
        return r.content


async def stream(ws, pcm):
    """Send audio in 20ms frames, paced against the wall clock like a real mic."""
    start = time.perf_counter()
    for n, i in enumerate(range(0, len(pcm), 640)):
        await ws.send(pcm[i:i + 640])
        await asyncio.sleep(max(0, start + (n + 1) * 0.02 - time.perf_counter()))


async def main():
    parts = [await speech(part) for part in QUESTION.split(" ... ")]
    clip = silence(1000).join(parts)  # a pause in the middle of the sentence, if asked for
    pcm = clip if BUTTON else silence(600) + clip + silence(2500)
    speech_end_ms = len(pcm) / 32 if BUTTON else 600 + len(clip) / 32
    interrupt_pcm = await speech(INTERRUPT) if INTERRUPT else None
    then_pcm = await speech(THEN) if THEN else None

    async with websockets.connect(SERVER, max_size=None) as ws:
        t0 = time.perf_counter()
        now = lambda: (time.perf_counter() - t0) * 1000
        first_audio = None
        played_until = None   # wall time when the reply audio was paused or cleared
        spoke = False         # has our question been sent yet (audio before that is the greeting)
        spoke_then = False    # has the follow-up turn been sent

        async def reader():
            nonlocal first_audio, played_until, spoke
            async for m in ws:
                if isinstance(m, bytes):
                    if first_audio is None and (BUTTON or spoke):
                        first_audio = now()
                        end = speech_end_ms + (0 if BUTTON else 3500)
                        print(f"  first audio @ {first_audio:.0f} ms  ->  V2V from end of speech: {first_audio - end:.0f} ms")
                    continue
                d = json.loads(m)
                if d["type"] == "transcript":
                    print(f"  [{'final' if d['final'] else 'interim'} @ {now():.0f}] {d['text']}")
                elif d["type"] in ("speech_start", "speech_end"):
                    print(f"  {d['type']} @ {now():.0f} ms")
                    if d["type"] == "speech_end":
                        spoke = True  # the next audio is the reply, not the greeting
                elif d["type"] == "pause_audio":
                    played_until = now()
                    print(f"  pause_audio @ {now():.0f} ms (after {d['after_ms']} ms of speech)")
                elif d["type"] == "resume_audio":
                    print(f"  resume_audio @ {now():.0f} ms")
                elif d["type"] == "clear_audio":
                    played = (played_until or now()) - first_audio  # like the browser: how much was heard
                    await ws.send(json.dumps({"type": "played", "ms": played}))
                    print(f"  clear_audio @ {now():.0f} ms, heard {played:.0f} ms of the reply")
                elif d["type"] == "turn_done" and d.get("greeting"):
                    print(f"  canned line done @ {now():.0f} ms")
                    if IDLE:
                        await asyncio.sleep(2)  # pretend it played
                        await ws.send(json.dumps({"type": "playback_done"}))
                    elif spoke:
                        return  # the reply to our question was a canned line
                elif d["type"] in ("turn_done", "error"):
                    print("  reply:", d.get("reply"), f"(tool {d['tool_ms']} ms)" if d.get("tool_ms") else "")
                    print("  timings:", d.get("timings", d.get("message")))
                    if INTERRUPT and first_audio and not played_until:
                        continue  # keep going, the interruption comes after this reply started
                    if then_pcm is not None and not spoke_then:
                        return  # main() sends the follow-up turn
                    return

        reading = asyncio.create_task(reader())
        if IDLE:
            try:
                await reading
            except websockets.ConnectionClosed:
                pass
            print(f"  server closed the session @ {now():.0f} ms")
            return
        if BUTTON:
            await ws.send(json.dumps({"type": "start"}))
        print(f"speech ends @ {speech_end_ms + (0 if BUTTON else 3500):.0f} ms")
        if not BUTTON:
            await asyncio.sleep(3.5)  # let the greeting play out before we speak
            await ws.send(json.dumps({"type": "playback_done"}))
        await stream(ws, pcm)
        if BUTTON:
            await ws.send(json.dumps({"type": "end_of_speech"}))

        if INTERRUPT:
            while first_audio is None:
                await asyncio.sleep(0.05)
            await asyncio.sleep(1.5)  # let the agent talk for a bit, then talk over it
            print(f"interrupting @ {now():.0f} ms with {INTERRUPT!r}")
            await stream(ws, interrupt_pcm + silence(3000))
        await reading

        if then_pcm is not None:
            await asyncio.sleep(2)  # pretend the reply finished playing
            await ws.send(json.dumps({"type": "playback_done"}))
            spoke_then = True
            first_audio = None
            print(f"follow-up @ {now():.0f} ms: {THEN!r}")
            reading = asyncio.create_task(reader())
            await stream(ws, silence(300) + then_pcm + silence(2500))
            await reading


asyncio.run(main())
