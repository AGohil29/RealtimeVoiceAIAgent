"""Percentiles per stage from traces.jsonl (one JSON object per completed turn).

    python benchmarks/analyze.py            # reads ./traces.jsonl
    python benchmarks/analyze.py path.jsonl

Report p50 / p95 / p99, never averages: one slow turn hidden in an average is a turn the
user still had to sit through.
"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "traces.jsonl"
turns = [json.loads(line) for line in open(path) if line.strip()]

# every mark except the first two is cumulative, counted from the end-of-turn decision
STAGES = [
    ("turn_detection", "Turn detection (last word -> decision)"),
    ("first_audio", "First audio, from real end of speech"),
    ("llm_first_token", "  decision -> LLM first token"),
    ("llm_first_sentence", "  decision -> LLM first sentence"),
    ("tts_first_byte", "  decision -> TTS first byte"),
    ("audio_sent", "  decision -> last audio sent"),
]


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, round(p / 100 * (len(values) - 1)))]


print(f"{len(turns)} turns from {path}\n")
print(f"{'stage':40s} {'p50':>6s} {'p95':>6s} {'p99':>6s}")
for key, label in STAGES:
    values = [t[key] for t in turns if key in t]
    if values:
        print(f"{label:40s} {percentile(values, 50):6.0f} {percentile(values, 95):6.0f} {percentile(values, 99):6.0f}")
