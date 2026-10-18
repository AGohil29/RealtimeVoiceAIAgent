# Real-Time Voice AI Agent

A browser-based voice agent built step by step, one phase per branch, from a 5 second
batch pipeline down to under 1 second voice-to-voice. Every phase adds one idea, measures
it, and leaves a small readable diff.

Design reference: [Design a Real-Time Voice AI Agent](https://outcomeschool.com/blog/design-a-real-time-voice-ai-agent)

Built for teaching at **Outcome School** by **Amit Shekhar** as part of the: [AI and Machine Learning Program](https://outcomeschool.com/program/ai-and-machine-learning)

## How to run

Needs Python 3.11+, Chrome, a [Deepgram](https://deepgram.com) API key (speech to text
and text to speech) and an [OpenRouter](https://openrouter.ai) API key (LLM).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add DEEPGRAM_API_KEY and OPENROUTER_API_KEY
uvicorn server.main:app --reload
```

Open http://localhost:8000 in Chrome, click **Start** and allow the microphone.
