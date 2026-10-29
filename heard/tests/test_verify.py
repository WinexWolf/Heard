"""Each verifier assertion: the reference fix passes AND the unpatched page fails (no rubber stamp)."""
import json
import pytest
from heard.app.pipeline import oracle, verify
from .conftest import ROOT

CASES = []
for site in ["shop", "signup", "dashboard"]:
    steps = json.loads((ROOT / f"data/sessions/{site}_buggy/steps.json").read_text())
    for b, step, f in oracle.oracle_findings(site, steps):
        CASES.append(pytest.param(site, b["id"], f.issue_type, step["selector"], id=f"{b['id']}-{f.issue_type}"))


@pytest.mark.parametrize("site,bug,itype,sel", CASES)
def test_reference_fix_passes(site, bug, itype, sel):
    r = verify.verify_edits(ROOT / f"demo_sites/{site}/buggy", oracle.oracle_edits(site, bug), itype, sel)
    assert r["passed"], r["reason"]
    assert r["new_violations"] == []


@pytest.mark.parametrize("site,bug,itype,sel", CASES)
def test_unpatched_page_fails(site, bug, itype, sel):
    r = verify.verify_edits(ROOT / f"demo_sites/{site}/buggy", [], itype, sel)
    assert not r["passed"]


def test_bad_patch_is_reported_not_raised():
    from heard.app.schemas import Edit
    r = verify.verify_edits(ROOT / "demo_sites/shop/buggy", [Edit(file="index.html", old_str="nope", new_str="x")], "missing_name", "#cart-btn")
    assert not r["passed"] and "could not be applied" in r["reason"]


def test_new_axe_violation_fails_a_fix():
    """A patch that fixes the name but adds an axe violation (duplicate id) must be rejected."""
    from heard.app.schemas import Edit
    e = Edit(file="index.html", old_str='<button id="cart-btn" class="icon-btn" type="button">',
             new_str='<button id="cart-btn" class="icon-btn" type="button" aria-label="Cart" aria-hidden="true">')
    r = verify.verify_edits(ROOT / "demo_sites/shop/buggy", [e], "missing_name", "#cart-btn")
    assert not r["passed"]


def test_new_violations_helper():
    assert verify.new_violations({"a": 1}, {"a": 1, "b": 2}) == ["b (2 vs 0)"]
    assert verify.new_violations({"a": 2}, {"a": 1}) == []


def test_verifications_run_one_browser_at_a_time(monkeypatch):
    """Two live runs must not launch two Chromiums at once (one peaks near 400 MiB on a 512 MiB host)."""
    import threading, time
    active, peak, lock = [0], [0], threading.Lock()
    def fake(*a, **k):
        with lock: active[0] += 1; peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock: active[0] -= 1
        return {"passed": True}
    monkeypatch.setattr(verify, "_verify_edits", fake)
    ts = [threading.Thread(target=verify.verify_edits, args=(None, [], "missing_name", "#x")) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert peak[0] == 1
