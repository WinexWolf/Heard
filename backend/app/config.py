from __future__ import annotations
import json, os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"


def _clean(v: str | None) -> str:
    return (v or "").split("#")[0].strip()


def _ph(v: str) -> bool:
    return (not v) or v.startswith("<")


class Settings:
    def __init__(self):
        self.base_url = _clean(os.getenv("NEBIUS_BASE_URL")).rstrip("/")
        self.api_key = _clean(os.getenv("NEBIUS_API_KEY"))
        self.tavily_key = _clean(os.getenv("TAVILY_API_KEY"))
        self.models = {"perception": _clean(os.getenv("MODEL_PERCEPTION")),
                       "patch": _clean(os.getenv("MODEL_PATCH")),
                       "escalation": _clean(os.getenv("MODEL_ESCALATION"))}
        self.prices = {}
        for role in self.models:
            def f(name):
                v = _clean(os.getenv(f"PRICE_PER_1M_{name}_{role.upper()}"))
                try: return float(v)
                except ValueError: return None
            self.prices[self.models[role] or role] = (f("INPUT"), f("OUTPUT"))
        self.rate_limit = int(_clean(os.getenv("RATE_LIMIT_ANALYSES_PER_HOUR")) or 6)
        self.demo_cache = (_clean(os.getenv("DEMO_MODE_CACHE")) or "true").lower() == "true"

    @property
    def live_ready(self) -> bool:
        return not any(_ph(x) for x in (self.api_key, self.base_url, self.tavily_key, *self.models.values()))

    def capabilities(self) -> dict:
        p = DATA / "capabilities.json"
        caps = json.loads(p.read_text()) if p.exists() else {"PERCEPTION_MODE": "text_only_log"}
        caps["models"] = {k: (v if not _ph(v) else None) for k, v in self.models.items()}
        caps["live_ready"] = self.live_ready
        return caps


def get_settings() -> Settings:
    return Settings()
