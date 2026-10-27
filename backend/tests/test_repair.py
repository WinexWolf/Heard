"""Repair -> escalation flow with a scripted LLM and the real verifier."""
import json
from backend.app.pipeline import run
from backend.app.schemas import Finding
from .conftest import FakeLLM, StubSettings, ROOT

F = Finding(id="F1", t_start=21.6, t_end=23, announced_text="button", visible_text_or_description="cart icon", issue_type="missing_name",
            severity="high", wcag_guess="4.1.2", evidence="")
STEP = {"selector": "#cart-btn", "html": "<button id=\"cart-btn\">", "name": "", "role": "button", "announcement": "button"}
BAD = json.dumps({"edits": [{"file": "index.html", "old_str": "NOT PRESENT", "new_str": "x"}], "rationale": "bad"})
GOOD = json.dumps({"edits": [{"file": "index.html", "old_str": '<button id="cart-btn" class="icon-btn" type="button">',
                              "new_str": '<button id="cart-btn" class="icon-btn" type="button" aria-label="Open cart">'}], "rationale": "label it"})
SITE = ROOT / "demo_sites/shop/buggy"


def go(llm, tmp_path):
    return run.fix_one(llm, StubSettings(), None, F, STEP, SITE, [], tmp_path, lambda e: None)


def test_first_try_success(tmp_path):
    llm = FakeLLM({"patch": [GOOD], "escalation": []})
    r = go(llm, tmp_path)
    assert r["fixed"] and r["model_used"] == "m-super" and len(r["attempts"]) == 1


def test_one_repair_attempt_then_success(tmp_path):
    llm = FakeLLM({"patch": [BAD, GOOD], "escalation": []})
    r = go(llm, tmp_path)
    assert r["fixed"] and len(r["attempts"]) == 2 and llm.calls[-1][1] == "patch"


def test_escalates_to_ultra_after_two_failures(tmp_path):
    llm = FakeLLM({"patch": [BAD, BAD], "escalation": [GOOD]})
    r = go(llm, tmp_path)
    assert r["fixed"] and r["model_used"] == "m-ultra" and len(r["attempts"]) == 3


def test_gives_up_after_escalation_fails(tmp_path):
    llm = FakeLLM({"patch": [BAD, BAD], "escalation": [BAD]})
    r = go(llm, tmp_path)
    assert not r["fixed"] and r["model_used"] is None and len(r["attempts"]) == 3
