"""heard CLI: speech snapshots, diffs, change-only audits, the token cache and the pass/fail decision."""
import json, shutil
import pytest
from heard.app import a11y, cli, driver, speechdiff
from .conftest import FakeLLM, ROOT

FLOWS = {"signup-submit": {"page": "/signup/", "steps": ["tab", "tab", "tab", "tab", "space", "tab", "enter"]}}
CFG = {**cli.DEFAULTS, "url": "unused"}


def app(tmp, variant):
    """Two-page app: the demo shop at / and the signup form at /signup/."""
    d = tmp / variant
    shutil.copytree(ROOT / f"demo_sites/shop/{variant}", d)
    shutil.copytree(ROOT / f"demo_sites/signup/{variant}", d / "signup")
    return d


@pytest.fixture(scope="module")
def snaps(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("apps")
    out = {}
    for v in ("fixed", "buggy"):
        with a11y.serve_dir(app(tmp, v)) as base:
            out[v] = driver.snapshot(base, ["/", "/signup/"], FLOWS)
    return out


def finding(t, heard, issue="missing_name", sev="high"):
    return {"id": f"F{t}", "t_start": t, "t_end": t, "announced_text": heard, "visible_text_or_description": "cart icon",
            "issue_type": issue, "severity": sev, "wcag_guess": "4.1.2", "evidence": ""}


def test_tab_order_and_flow_are_recorded(snaps):
    fixed = snaps["fixed"]["pages"]
    assert "Open cart, 5 items, button" in [s["announcement"] for s in fixed["/"]]
    flow = [s["announcement"] for s in fixed["flow:signup-submit"]]
    assert "I agree to the terms, check box, checked" in flow and flow[-1] == "Enter a valid email address."


def test_diff_marks_only_what_users_hear_differently(snaps):
    d = speechdiff.diff(snaps["fixed"], snaps["buggy"])
    assert {k for k, c in d.items() if c["status"] == "changed"} == {"/", "/signup/", "flow:signup-submit"}
    notes = d["/"]["notes"]
    cart = next(i for i, s in enumerate(snaps["buggy"]["pages"]["/"]) if s["announcement"] == "button")
    assert 'previously_heard="Open cart, 5 items, button"' in notes[cart]
    assert all(n.startswith(("previously_heard", "(new step)", "no_longer")) for n in notes.values())
    assert speechdiff.diff(snaps["fixed"], snaps["fixed"])["/"]["notes"] == {}


def test_check_audits_changed_pages_once_then_uses_cache(snaps, tmp_path):
    head = snaps["buggy"]; cart = next(s["i"] for s in head["pages"]["/"] if s["announcement"] == "button")
    shop_reply = json.dumps({"findings": [finding(cart, "button"), finding(cart, "Buy now, button")]})  # 2nd is invented
    llm = FakeLLM({"perception": [shop_reply, '{"findings": []}', '{"findings": []}']})
    cache = tmp_path / "cache.json"
    rep = cli.run_check(CFG, snaps["fixed"], head, llm, cache)
    assert rep["result"] == "fail" and rep["model_calls"] == 3 and rep["failing"] == 1
    assert rep["findings"][0]["page"] == "/" and rep["findings"][0]["step"] == "button"
    assert len(rep["rejected_unsupported"]) == 1                       # the invented quote is not in the speech log
    again = cli.run_check(CFG, snaps["fixed"], head, FakeLLM({"perception": []}), cache)
    assert again["model_calls"] == 0 and again["findings"] == rep["findings"]


def test_unchanged_push_costs_nothing_and_passes(snaps):
    rep = cli.run_check(CFG, snaps["fixed"], snaps["fixed"], FakeLLM({"perception": []}))
    assert rep["result"] == "pass" and rep["model_calls"] == 0 and rep["changed_steps"] == 0


def test_low_severity_does_not_fail_and_no_key_is_reported_as_unaudited(snaps):
    head = snaps["buggy"]; cart = next(s["i"] for s in head["pages"]["/"] if s["announcement"] == "button")
    llm = FakeLLM({"perception": [json.dumps({"findings": [finding(cart, "button", sev="low")]}), '{"findings": []}', '{"findings": []}']})
    assert cli.run_check(CFG, snaps["fixed"], head, llm)["result"] == "pass"
    assert cli.run_check(CFG, snaps["fixed"], head, None)["result"] == "unaudited"


def test_markdown_report_lists_regressions_and_speech_changes(snaps):
    head = snaps["buggy"]; cart = next(s["i"] for s in head["pages"]["/"] if s["announcement"] == "button")
    llm = FakeLLM({"perception": [json.dumps({"findings": [finding(cart, "button")]}), '{"findings": []}', '{"findings": []}']})
    md = cli.markdown(cli.run_check(CFG, snaps["fixed"], head, llm), "origin/main:heard.snapshot.json")
    assert md.startswith("## ❌ Heard: 1 accessibility regression(s)")
    assert "| `/` | “button” | missing name: cart icon | high | 4.1.2 |" in md
    assert "“Open cart, 5 items, button" in md


def test_report_page_renders_from_file_and_is_accessible(snaps, tmp_path):
    from playwright.sync_api import sync_playwright
    from heard.app import report
    head = snaps["buggy"]; cart = next(s["i"] for s in head["pages"]["/"] if s["announcement"] == "button")
    f = finding(cart, "button"); f["visible_text_or_description"] = "cart icon </script><b>not markup</b>"   # must stay inert data
    llm = FakeLLM({"perception": [json.dumps({"findings": [f]}), '{"findings": []}', '{"findings": []}']})
    page_file = report.write({**cli.run_check(CFG, snaps["fixed"], head, llm), "base": "origin/main"}, tmp_path / "report.html")
    with sync_playwright() as pw:
        b = pw.chromium.launch(**a11y.chromium_launch_kwargs()); pg = b.new_page()
        pg.goto(page_file.as_uri())
        assert pg.get_by_role("heading", level=1).inner_text() == "1 accessibility regression"
        assert pg.get_by_text("cart icon </script><b>not markup</b>").is_visible()
        assert pg.get_by_role("region", name="/signup/").is_visible()
        pg.add_script_tag(path=str(a11y.AXE_JS))
        for theme in ["Light", "Dark"]:
            pg.get_by_role("group", name="Appearance").get_by_role("button", name=theme).click()
            v = pg.evaluate("axe.run().then(r => r.violations.map(v => v.id + ': ' + v.help))")
            assert v == [], f"report {theme}: {v}"
        b.close()


def test_audit_cache_is_keyed_by_model_and_prompt_and_expires(snaps, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from heard.app.pipeline import perception
    empty = ['{"findings": []}'] * 3
    def llm(model):
        f = FakeLLM({"perception": list(empty)}); f.s = SimpleNamespace(models={"perception": model}); return f
    cache = tmp_path / "cache.json"
    assert cli.run_check(CFG, snaps["fixed"], snaps["buggy"], llm("omni-a"), cache)["model_calls"] == 3
    assert cli.run_check(CFG, snaps["fixed"], snaps["buggy"], llm("omni-a"), cache)["model_calls"] == 0     # same model: cached
    assert cli.run_check(CFG, snaps["fixed"], snaps["buggy"], llm("omni-b"), cache)["model_calls"] == 3     # new model: re-audit
    monkeypatch.setattr(perception, "SYSTEM", perception.SYSTEM + "\nBe stricter.")
    assert cli.run_check(CFG, snaps["fixed"], snaps["buggy"], llm("omni-b"), cache)["model_calls"] == 3     # new prompt: re-audit
    stale = {h: {**e, "at": 0} for h, e in json.loads(cache.read_text()).items()}
    cache.write_text(json.dumps(stale))
    assert cli.run_check(CFG, snaps["fixed"], snaps["buggy"], llm("omni-b"), cache)["model_calls"] == 3     # expired: re-audit
