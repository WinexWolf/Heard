from heard.app.ratelimit import RateLimiter
from heard.app.llm import CostTracker


def test_rate_limiter_blocks_then_recovers():
    now = [1000.0]
    rl = RateLimiter(2, window=3600, clock=lambda: now[0])
    assert rl.check("1.1.1.1")[0] and rl.check("1.1.1.1")[0]
    ok, retry = rl.check("1.1.1.1")
    assert not ok and 0 < retry <= 3600
    assert rl.check("2.2.2.2")[0]            # other clients unaffected
    now[0] += 3601
    assert rl.check("1.1.1.1")[0]


def test_cost_tracker_totals_and_split():
    t = CostTracker({"nano": (0.10, 0.40), "super": (0.30, 1.20)})
    t.record("perception", "nano", 1_000_000, 500_000, 2.0)
    t.record("patch", "super", 200_000, 100_000, 1.0)
    t.record("patch", "unpriced", 10, 10, 0.5)
    s = t.summary()
    assert s["by_model"]["nano"]["cost_usd"] == 0.3 and s["by_stage"]["patch"]["calls"] == 2
    assert s["total"]["calls"] == 3 and s["total"]["cost_known"] is False and s["total"]["input_tokens"] == 1_200_010
    assert abs(s["by_model"]["super"]["cost_usd"] - 0.18) < 1e-9


def test_tavily_calls_are_logged():
    t = CostTracker(); t.record_tavily("q", 0.4, 3)
    assert t.summary()["total"]["tavily_calls"] == 1 and t.summary()["tavily"][0]["query"] == "q"


def test_npm_launcher_version_matches_python_package():
    """npx heard runs `uvx heard==<npm version>`, so the two releases must share a version."""
    import json, tomllib
    from .conftest import ROOT
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert json.loads((ROOT / "npm/package.json").read_text())["version"] == py


def test_each_role_is_sent_to_its_provider(monkeypatch):
    from heard.app.config import Settings, NVIDIA_BASE_URL
    for k, v in {"NEBIUS_BASE_URL": "https://neb/v1/", "NEBIUS_API_KEY": "nk", "NVIDIA_API_KEY": "vk", "PERCEPTION_PROVIDER": "nvidia",
                 "MODEL_PERCEPTION": "omni", "MODEL_PATCH": "super", "MODEL_ESCALATION": "ultra", "TAVILY_API_KEY": "t"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PATCH_PROVIDER", raising=False); monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
    s = Settings()
    assert s.endpoint("perception") == (NVIDIA_BASE_URL, "vk") and s.endpoint("patch") == ("https://neb/v1", "nk")
    assert s.live_ready
    monkeypatch.setenv("NVIDIA_API_KEY", "<YOUR_NVIDIA_API_KEY>")
    assert not Settings().role_ready("perception") and Settings().role_ready("patch")


def test_busy_provider_is_retried_then_succeeds(monkeypatch):
    from types import SimpleNamespace
    from heard.app import llm as llmmod
    replies = [SimpleNamespace(status_code=503, text="busy"), SimpleNamespace(status_code=429, text="slow down"),
               SimpleNamespace(status_code=200, text="", json=lambda: {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})]
    sent = []
    monkeypatch.setattr(llmmod.httpx, "post", lambda url, json, timeout, headers: (sent.append((url, json)), replies.pop(0))[1])
    s = SimpleNamespace(models={"perception": "omni"}, prices={}, endpoint=lambda role: ("https://nv/v1", "k"))
    waits = []
    llm = llmmod.LLM(s, sleep=waits.append)
    assert llm.chat("perception", "perception", [], extra={"mm_processor_kwargs": {"use_audio_in_video": True}}) == "ok"
    assert waits == [1, 2] and len(sent) == 3 and sent[0][0] == "https://nv/v1/chat/completions"
    assert sent[0][1]["mm_processor_kwargs"] == {"use_audio_in_video": True}
    assert llm.tracker.calls[-1].note == "2 retries"


def test_timeouts_are_retried_and_reported_with_the_retry_count(monkeypatch):
    from types import SimpleNamespace
    import httpx, pytest
    from heard.app import llm as llmmod
    calls = []
    def post(url, json, timeout, headers):
        calls.append(1)
        if len(calls) < 3: raise httpx.ReadTimeout("slow")
        return SimpleNamespace(status_code=200, text="", json=lambda: {"choices": [{"message": {"content": "ok"}}], "usage": {}})
    monkeypatch.setattr(llmmod.httpx, "post", post)
    s = SimpleNamespace(models={"perception": "omni"}, prices={}, endpoint=lambda role: ("https://nv/v1", "k"))
    assert llmmod.LLM(s, sleep=lambda _: None).chat("perception", "perception", []) == "ok" and len(calls) == 3
    monkeypatch.setattr(llmmod.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ReadTimeout("slow")))
    with pytest.raises(llmmod.LLMError, match="ReadTimeout, 2 retries"):
        llmmod.LLM(s, retries=2, sleep=lambda _: None).chat("perception", "perception", [])
