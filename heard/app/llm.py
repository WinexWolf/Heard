"""Token Factory (OpenAI-compatible) client wrapped with a cost / latency tracker."""
from __future__ import annotations
import time, threading
from dataclasses import dataclass, asdict, field
import httpx
from .config import Settings, get_settings


@dataclass
class Call:
    stage: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    cost_usd: float | None
    ok: bool = True
    note: str = ""


class CostTracker:
    def __init__(self, prices: dict[str, tuple[float | None, float | None]] | None = None):
        self.prices = prices or {}
        self.calls: list[Call] = []
        self.tavily_calls: list[dict] = []
        self._lock = threading.Lock()

    def cost(self, model: str, tin: int, tout: int) -> float | None:
        pi, po = self.prices.get(model, (None, None))
        if pi is None or po is None:
            return None
        return (tin * pi + tout * po) / 1_000_000

    def record(self, stage, model, tin, tout, latency, ok=True, note="") -> Call:
        c = Call(stage, model, tin, tout, round(latency, 3), self.cost(model, tin, tout), ok, note)
        with self._lock: self.calls.append(c)
        return c

    def record_tavily(self, query: str, latency: float, n: int, ok=True):
        with self._lock: self.tavily_calls.append({"query": query, "latency_s": round(latency, 3), "results": n, "ok": ok})

    def summary(self) -> dict:
        def agg(keyfn):
            out: dict = {}
            for c in self.calls:
                a = out.setdefault(keyfn(c), {"calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_s": 0.0, "cost_usd": 0.0, "cost_known": True})
                a["calls"] += 1; a["input_tokens"] += c.input_tokens; a["output_tokens"] += c.output_tokens
                a["latency_s"] = round(a["latency_s"] + c.latency_s, 3)
                if c.cost_usd is None: a["cost_known"] = False
                else: a["cost_usd"] = round(a["cost_usd"] + c.cost_usd, 6)
            return out
        total_cost = sum(c.cost_usd or 0 for c in self.calls)
        return {"total": {"calls": len(self.calls), "input_tokens": sum(c.input_tokens for c in self.calls),
                          "output_tokens": sum(c.output_tokens for c in self.calls),
                          "latency_s": round(sum(c.latency_s for c in self.calls), 3),
                          "cost_usd": round(total_cost, 6),
                          "cost_known": all(c.cost_usd is not None for c in self.calls) if self.calls else True,
                          "tavily_calls": len(self.tavily_calls)},
                "by_stage": agg(lambda c: c.stage), "by_model": agg(lambda c: c.model),
                "calls": [asdict(c) for c in self.calls], "tavily": self.tavily_calls}


class LLMError(RuntimeError):
    pass


class LLM:
    """chat(stage, role, messages) -> text. `role` selects the model and its provider: perception / patch / escalation.
    Busy providers (HTTP 429/503, common on NVIDIA's shared endpoint) are retried with exponential backoff."""
    RETRY_STATUS = (429, 503)
    TIMEOUT = httpx.Timeout(connect=30, read=600, write=120, pool=30)   # perception on a busy shared endpoint can take minutes

    def __init__(self, settings: Settings | None = None, tracker: CostTracker | None = None, retries: int = 5, sleep=time.sleep):
        self.s = settings or get_settings()
        self.tracker = tracker or CostTracker(self.s.prices)
        self.retries, self.sleep = retries, sleep

    def chat(self, stage: str, role: str, messages: list[dict], max_tokens: int = 4096, temperature: float = 0.2,
             extra: dict | None = None) -> str:
        """`extra` is merged into the request body, e.g. {"mm_processor_kwargs": {"use_audio_in_video": True}}."""
        model = self.s.models[role]
        base_url, api_key = self.s.endpoint(role)
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, **(extra or {})}
        t0 = time.time()
        for attempt in range(self.retries + 1):
            try:
                r = httpx.post(f"{base_url}/chat/completions", json=body, timeout=self.TIMEOUT, headers={"Authorization": f"Bearer {api_key}"})
            except httpx.TransportError as e:            # timeouts and dropped connections are as transient as a 503
                if attempt == self.retries:
                    self.tracker.record(stage, model, 0, 0, time.time() - t0, ok=False, note=f"{type(e).__name__} after {attempt} retries")
                    raise LLMError(f"network error calling model ({type(e).__name__}, {attempt} retries)") from None
                self.sleep(min(30, 2 ** attempt)); continue
            if r.status_code not in self.RETRY_STATUS or attempt == self.retries:
                break
            self.sleep(min(30, 2 ** attempt))
        dt = time.time() - t0
        if r.status_code != 200:
            self.tracker.record(stage, model, 0, 0, dt, ok=False, note=f"HTTP {r.status_code}")
            raise LLMError(f"model call failed: HTTP {r.status_code}: {r.text[:300]}")
        j = r.json()
        u = j.get("usage") or {}
        self.tracker.record(stage, model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), dt, note=f"{attempt} retries" if attempt else "")
        return j["choices"][0]["message"].get("content") or ""
