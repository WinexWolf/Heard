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


NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class Settings:
    """Each model role runs on a provider: Nebius Token Factory (default) or NVIDIA's API (`{ROLE}_PROVIDER=nvidia`).
    Token Factory accepts text, image and video only, so audio perception runs on Nemotron Omni via NVIDIA."""
    def __init__(self):
        self.base_url = _clean(os.getenv("NEBIUS_BASE_URL")).rstrip("/")
        self.api_key = _clean(os.getenv("NEBIUS_API_KEY"))
        self.providers = {"nebius": (self.base_url, self.api_key),
                          "nvidia": ((_clean(os.getenv("NVIDIA_BASE_URL")) or NVIDIA_BASE_URL).rstrip("/"), _clean(os.getenv("NVIDIA_API_KEY")))}
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
        self.provider = {role: (_clean(os.getenv(f"{role.upper()}_PROVIDER")) or "nebius").lower() for role in self.models}
        # optional cap on a reasoning model's thinking tokens (sent as chat_template_kwargs.thinking_token_budget)
        self.thinking_budget = {role: int(v) if (v := _clean(os.getenv(f"{role.upper()}_THINKING_BUDGET"))).isdigit() else None
                                for role in self.models}
        self.rate_limit = int(_clean(os.getenv("RATE_LIMIT_ANALYSES_PER_HOUR")) or 6)
        self.demo_cache = (_clean(os.getenv("DEMO_MODE_CACHE")) or "true").lower() == "true"

    def endpoint(self, role: str) -> tuple[str, str]:
        """(base_url, api_key) for the provider that serves `role`."""
        return self.providers.get(self.provider[role], ("", ""))

    def role_ready(self, role: str) -> bool:
        return not any(_ph(x) for x in (*self.endpoint(role), self.models[role]))

    @property
    def live_ready(self) -> bool:
        return not _ph(self.tavily_key) and all(self.role_ready(r) for r in self.models)

    def capabilities(self) -> dict:
        p = DATA / "capabilities.json"
        caps = json.loads(p.read_text()) if p.exists() else {"PERCEPTION_MODE": "text_only_log"}
        caps["models"] = {k: (v if not _ph(v) else None) for k, v in self.models.items()}
        caps["providers"] = dict(self.provider)
        caps["live_ready"] = self.live_ready
        return caps


def get_settings() -> Settings:
    return Settings()
