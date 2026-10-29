"""Repair -> escalation flow with a scripted LLM and the real verifier."""
import json
from heard.app.pipeline import run
from heard.app.schemas import Finding
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


def test_duplicate_findings_are_merged_before_patching():
    steps = [{"t": 10.0, "selector": ".tabs > div.tab:nth-of-type(1)", "announcement": "Overview, clickable"},
             {"t": 12.0, "selector": ".tabs > div.tab:nth-of-type(2)", "announcement": "Orders, clickable"},
             {"t": 20.0, "selector": "li:nth-of-type(1) > button.edit-btn", "announcement": "Edit, button"},
             {"t": 21.0, "selector": "li:nth-of-type(2) > button.edit-btn", "announcement": "Edit, button"},
             {"t": 30.0, "selector": "#export", "announcement": "Export CSV, clickable"},
             {"t": 31.0, "selector": "#settings", "announcement": "Settings, clickable"}]
    mk = lambda i, t, kind, heard: Finding(id=f"F{i}", t_start=t, t_end=t, announced_text=heard, visible_text_or_description="",
                                           issue_type=kind, severity="high", wcag_guess="", evidence="")
    found = [mk(1, 10, "tab_widget", "Overview, clickable"), mk(2, 12, "tab_widget", "Orders, clickable"),      # one widget
             mk(3, 20, "repeated_control", "Edit, button"), mk(4, 21, "repeated_control", "Edit, button"),     # one group
             mk(5, 30, "div_button", "Export CSV, clickable"), mk(6, 31, "div_button", "Settings, clickable")]  # two elements
    kept, merged = run.dedupe(found, steps)
    assert [f.id for f in kept] == ["F1", "F3", "F5", "F6"]
    assert [(m["finding"]["id"], m["duplicate_of"]) for m in merged] == [("F2", "F1"), ("F4", "F3")]


def _f(kind, heard="x"):
    return Finding(id="F", t_start=0, t_end=0, announced_text=heard, visible_text_or_description="", issue_type=kind,
                   severity="high", wcag_guess="", evidence="model said so")


def test_mistyped_findings_are_corrected_by_element_role():
    button = {"role": "button", "name": "Continue", "visible_text": "Create account"}
    f = run.fit_type(_f("vague_link", "Continue, button"), button)              # the live signup mislabel
    assert f.issue_type == "label_in_name" and "type corrected" in f.evidence
    assert run.fit_type(_f("vague_link"), {"role": "link", "name": "Learn more", "visible_text": "Learn more"}).issue_type == "vague_link"
    assert run.fit_type(_f("missing_alt"), {"role": "button", "name": "Cart", "visible_text": "Cart"}).issue_type == "missing_alt"


def test_findings_the_unpatched_page_already_passes_are_not_reproduced():
    site = ROOT / "demo_sites/dashboard/buggy"
    assert "not reproduced" in run.not_reproduced(site, _f("div_button"), {"selector": "#open-modal"})   # a real <button>
    assert run.not_reproduced(site, _f("div_button"), {"selector": "#export"}) == ""                  # the real fake button


def test_state_failures_point_the_patch_model_at_javascript():
    from heard.app.pipeline import oracle, verify
    html_only = [e for e in oracle.oracle_edits("dashboard", "B08") if e.file == "index.html"]
    r = verify.verify_edits(ROOT / "demo_sites/dashboard/buggy", html_only, "tab_widget", "")
    assert not r["passed"] and "aria-selected does not follow the active tab" in r["reason"] and ".js file" in r["reason"]


def test_patch_prompt_forbids_abbreviated_search_text():
    from heard.app.pipeline import patch
    assert 'Never shorten it with "..."' in patch.SYSTEM and ".js file" in patch.SYSTEM
