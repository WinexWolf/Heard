from backend.app.ratelimit import RateLimiter
from backend.app.llm import CostTracker


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
