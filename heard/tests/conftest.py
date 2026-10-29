import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
ROOT = Path(__file__).resolve().parents[2]


class FakeLLM:
    """Scripted LLM: returns queued replies per role; records calls."""
    def __init__(self, replies):
        self.replies = {k: list(v) for k, v in replies.items()}; self.calls = []; self.extras = []
    def chat(self, stage, role, messages, max_tokens=0, temperature=0, extra=None):
        self.calls.append((stage, role)); self.extras.append(extra)
        return self.replies[role].pop(0)


class StubSettings:
    models = {"perception": "m-omni", "patch": "m-super", "escalation": "m-ultra"}


@pytest.fixture
def root():
    return ROOT
