import json
import time


class Trace:
    """Timing marks for one conversation turn. All values in milliseconds."""

    def __init__(self):
        self.t0 = time.perf_counter()
        self.marks = {}

    def mark(self, name):
        self.marks[name] = round((time.perf_counter() - self.t0) * 1000)

    def duration(self, start, end):
        return self.marks[end] - self.marks[start]

    def save(self, path="traces.jsonl"):
        with open(path, "a") as f:
            f.write(json.dumps(self.marks) + "\n")
