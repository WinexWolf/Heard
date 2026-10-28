"""heard fix: source locator, live verification against a running app, repair/escalation, and exact restores."""
import json, shutil
import pytest
from playwright.sync_api import sync_playwright
from heard.app import a11y, cli, driver, fixer
from .conftest import FakeLLM, ROOT

MODELS = {"perception": "m-omni", "patch": "m-super", "escalation": "m-ultra"}
CART = '<button id="cart-btn" class="icon-btn" type="button">'
GOOD = json.dumps({"edits": [{"file": "src/index.html", "old_str": CART, "new_str": CART.replace('type="button"', 'type="button" aria-label="Open cart"')}], "rationale": "name it"})
UNAPPLIABLE = json.dumps({"edits": [{"file": "src/index.html", "old_str": "NOT IN FILE", "new_str": "x"}], "rationale": "bad"})
NO_EFFECT = json.dumps({"edits": [{"file": "src/index.html", "old_str": CART, "new_str": CART.replace("icon-btn", "icon-btn cart")}], "rationale": "wrong"})


def project(tmp, variant="buggy"):
    """A repo whose dev server serves src/ straight from disk, so edits are live immediately (like hot reload)."""
    root = tmp / variant
    shutil.copytree(ROOT / f"demo_sites/shop/{variant}", root / "src")
    (root / "src/other.html").write_text("<p>About us</p>")
    shutil.copytree(root / "src", root / "src/node_modules/copy")            # must never be patched
    return root


@pytest.fixture
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch(**a11y.chromium_launch_kwargs()); yield b; b.close()


def run(root, browser, replies, keep=True, models=MODELS):
    with a11y.serve_dir(root / "src") as base:
        cfg = {**cli.DEFAULTS, "url": base, "src": ["src"], "fix_timeout": 1}
        snap = driver.snapshot(base, ["/"], browser=browser)
        cart = next(s["i"] for s in snap["pages"]["/"] if s["announcement"] == "button")
        rep = {"findings": [{"page": "/", "step": "button", "id": "F1", "t_start": cart, "t_end": cart, "announced_text": "button",
                             "visible_text_or_description": "cart icon", "issue_type": "missing_name", "severity": "high",
                             "wcag_guess": "4.1.2", "evidence": ""}], "fail_on": "medium"}
        llm = FakeLLM({"patch": list(replies), "escalation": [] if len(replies) < 3 else [replies[2]]})
        if len(replies) >= 3: llm.replies["patch"] = list(replies[:2])
        fixer.run_fix(cfg, rep, snap, llm, models, root, browser, keep=keep)
        return rep["findings"][0]["fix"], llm, snap


def test_locate_picks_the_elements_file_and_skips_node_modules(tmp_path):
    root = project(tmp_path)
    step = {"html": CART + "<svg", "visible_text": "", "name": ""}
    found = fixer.locate(root, ["src"], step)
    assert list(found)[0] == "src/index.html" and not any("node_modules" in p for p in found) and "src/other.html" not in found


def test_fix_repairs_once_then_keeps_the_verified_fix(tmp_path, browser):
    root = project(tmp_path)
    fix, llm, _ = run(root, browser, [UNAPPLIABLE, GOOD])
    assert fix["status"] == "fixed" and fix["kept"] and len(fix["attempts"]) == 2 and fix["model"] == "m-super"
    assert 'aria-label="Open cart"' in (root / "src/index.html").read_text()
    assert '+<button id="cart-btn" class="icon-btn" type="button" aria-label="Open cart">' in fix["diff"]
    assert fix["after_announcement"] == "Open cart, button"


def test_dry_run_verifies_then_reverts(tmp_path, browser):
    root = project(tmp_path); before = (root / "src/index.html").read_bytes()
    fix, _, _ = run(root, browser, [GOOD], keep=False)
    assert fix["status"] == "fixed" and not fix["kept"] and fix["diff"]
    assert (root / "src/index.html").read_bytes() == before


def test_unverified_fixes_are_restored_byte_for_byte_after_escalation(tmp_path, browser):
    root = project(tmp_path); before = (root / "src/index.html").read_bytes()
    fix, llm, _ = run(root, browser, [NO_EFFECT, NO_EFFECT, NO_EFFECT])
    assert fix["status"] == "failed" and [a["role"] for a in fix["attempts"]] == ["patch", "patch", "escalation"]
    assert "accessible name is still empty" in fix["reason"]
    assert (root / "src/index.html").read_bytes() == before


def test_already_fixed_page_costs_no_model_calls(tmp_path, browser):
    root = project(tmp_path, "buggy")
    with a11y.serve_dir(root / "src") as base:
        snap = driver.snapshot(base, ["/"], browser=browser)
    shutil.copy(ROOT / "demo_sites/shop/fixed/index.html", root / "src/index.html")   # someone already fixed it
    cart = next(s["i"] for s in snap["pages"]["/"] if s["announcement"] == "button")
    with a11y.serve_dir(root / "src") as base:
        cfg = {**cli.DEFAULTS, "url": base, "src": ["src"], "fix_timeout": 1}
        rep = {"findings": [{"page": "/", "id": "F1", "t_start": cart, "t_end": cart, "announced_text": "button", "visible_text_or_description": "",
                             "issue_type": "missing_name", "severity": "high", "wcag_guess": "4.1.2", "evidence": ""}], "fail_on": "medium"}
        llm = FakeLLM({"patch": []})
        fixer.run_fix(cfg, rep, snap, llm, MODELS, root, browser)
    assert rep["findings"][0]["fix"]["status"] == "already_fixed" and llm.calls == []
