"""Stage 4: deterministic verification (no LLM).

Verification is an accessibility-TREE PROXY for screen-reader output, not a live screen reader:
we apply the edits to a temp copy of the site, load it in Chromium, assert the property implied by the
finding type using the CDP accessibility tree, and require that axe-core reports no NEW violations.
"""
from __future__ import annotations
import re, shutil, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, Page
from .. import a11y
from .patch import apply_edits, PatchError

LAST_SEG = re.compile(r"[^>]+$")
# Appended when the missing behaviour lives in a script: the HTML alone cannot make state follow the user.
IN_JS = " (this changes at runtime: update the click/keydown handler in the site's .js file, not only the HTML)"


def group_selector(sel: str) -> str:
    m = LAST_SEG.search(sel or "")
    if not m: return ""
    seg = m.group(0).strip()
    return re.sub(r":nth-of-type\(\d+\)", "", seg)


def axe_counts(page: Page) -> dict[str, int]:
    a11y.add_axe(page)
    res = page.evaluate("axe.run().then(r => r.violations.map(v => [v.id, v.nodes.length]))")
    return {i: n for i, n in res}


def new_violations(before: dict[str, int], after: dict[str, int]) -> list[str]:
    return [f"{k} ({after[k]} vs {before.get(k, 0)})" for k in after if after[k] > before.get(k, 0)]


def _info(page, h): return a11y.ax_info(page, h)


def check_finding(page: Page, issue_type: str, selector: str) -> tuple[bool, str, list[str]]:
    checks: list[str] = []
    el = page.query_selector(selector) if selector else None
    grp = [h for h in page.query_selector_all(group_selector(selector))] if selector else []
    if issue_type not in ("modal_dialog", "tab_widget", "heading_skip") and el is None:
        return False, f"element for selector {selector!r} no longer found", checks

    if issue_type == "missing_label":
        # a placeholder alone is not a label (WCAG 3.3.2 / 1.3.1): require <label for>, aria-label or aria-labelledby
        has = page.evaluate("(e)=>!!((e.labels && e.labels.length) || e.getAttribute('aria-label') || e.getAttribute('aria-labelledby'))", el)
        i = _info(page, el); checks.append(f'programmatic label present = {has}; accessible name = {i["name"]!r}')
        return bool(has and i["name"]), "" if has else "input has no programmatic label (placeholder is not a label)", checks
    if issue_type in ("missing_name", "other"):
        i = _info(page, el); ok = bool(i["name"]); checks.append(f'accessible name = {i["name"]!r}')
        return ok, "" if ok else "accessible name is still empty", checks
    if issue_type == "missing_alt":
        alt = (el.get_attribute("alt") or "").strip(); ok = bool(alt) or el.get_attribute("role") in ("presentation", "none")
        checks.append(f"alt = {alt!r}")
        return ok, "" if ok else "img still has no alt text", checks
    if issue_type in ("vague_link", "repeated_control"):
        names = [_info(page, h)["name"].strip().lower() for h in grp]
        checks.append(f"names = {names}")
        ok = len(names) > 0 and all(names) and len(set(names)) == len(names)
        return ok, "" if ok else "controls still share the same (or an empty) accessible name", checks
    if issue_type == "label_in_name":
        i = _info(page, el); vis = i["text"].strip().lower(); nm = i["name"].lower()
        checks.append(f"visible={vis!r} name={nm!r}")
        ok = bool(vis) and vis in nm
        return ok, "" if ok else "accessible name does not contain the visible label (WCAG 2.5.3)", checks
    if issue_type == "div_button":
        i = _info(page, el); tab = page.evaluate("(e)=>e.tabIndex", el)
        checks.append(f'role={i["role"]} tabIndex={tab}')
        ok = i["role"] in ("button", "link") and tab >= 0
        return ok, "" if ok else "element is not exposed as a focusable button/link", checks
    if issue_type == "error_not_announced":
        static = page.evaluate("""(e)=>{ for (let n=e; n; n=n.parentElement){ const r=n.getAttribute('role'); const l=n.getAttribute('aria-live');
            if (['alert','status','log'].includes(r) || ['polite','assertive'].includes(l)) return true } return false }""", el)
        if static:
            checks.append("element is inside a live region / alert"); return True, "", checks
        # the step may point at the control that triggers the error: activate it and see whether a live region receives text
        el.click(); page.wait_for_timeout(200)
        live = page.evaluate("""()=>[...document.querySelectorAll('[role=alert],[role=status],[aria-live=polite],[aria-live=assertive]')].map(e=>e.innerText.trim()).filter(Boolean)""")
        checks.append(f"live region text after activating control: {live}")
        return bool(live), "" if live else "error text appears on screen but is not in a live region (role=alert / aria-live)", checks
    if issue_type == "missing_state":
        i = _info(page, el); attr = el.get_attribute("aria-checked")
        checks.append(f'role={i["role"]} aria-checked={attr}')
        if i["role"] not in ("checkbox", "switch", "radio", "menuitemcheckbox") or attr is None:
            return False, "no checkbox role / aria-checked state exposed", checks
        before = el.get_attribute("aria-checked"); el.click(); after = el.get_attribute("aria-checked")
        checks.append(f"after click aria-checked {before}->{after}")
        return before != after, "" if before != after else "aria-checked does not update when toggled" + IN_JS, checks
    if issue_type == "heading_skip":
        lv = page.evaluate("""()=>[...document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]')].filter(h=>h.offsetParent!==null)
            .map(h=>+(h.getAttribute('aria-level')||h.tagName.slice(1)))""")
        checks.append(f"heading levels {lv}")
        ok = all(b - a <= 1 for a, b in zip(lv, lv[1:])) and (not lv or lv[0] == 1)
        return ok, "" if ok else "heading levels still skip", checks
    if issue_type == "tab_widget":
        tl = page.query_selector("[role=tablist]"); tabs = page.query_selector_all("[role=tab]")
        if not tl or len(tabs) < 2: return False, "missing role=tablist / role=tab elements", checks
        sel = [t.get_attribute("aria-selected") for t in tabs]; checks.append(f"aria-selected {sel}")
        if None in sel or sel.count("true") != 1: return False, "tabs lack aria-selected (exactly one true)", checks
        tabs[1].click(); sel2 = [t.get_attribute("aria-selected") for t in tabs]; checks.append(f"after click {sel2}")
        ok = sel2[1] == "true" and sel2.count("true") == 1
        return ok, "" if ok else "aria-selected does not follow the active tab" + IN_JS, checks
    if issue_type == "modal_dialog":
        dlg = page.query_selector("[role=dialog],[role=alertdialog]")
        if not dlg: return False, "no element with role=dialog", checks
        for b in page.query_selector_all("button"):
            if not b.is_visible() or page.evaluate("([a,d])=>d.contains(a)", [b, dlg]): continue
            b.click(); page.wait_for_timeout(150)
            if dlg.is_visible():
                nm = _info(page, dlg)["name"]; checks.append(f"dialog name after opening = {nm!r}")
                inside = page.evaluate("(d)=>d.contains(document.activeElement)", dlg)
                checks.append(f"after opening, focus inside dialog = {inside}")
                if not nm: return False, "dialog has no accessible name", checks
                return bool(inside), "" if inside else "focus is not moved into the dialog when it opens" + IN_JS, checks
        return False, "could not open the dialog to test focus", checks
    return False, f"unknown issue_type {issue_type}", checks


def verify_edits(buggy_dir: Path, edits, issue_type: str, selector: str, entry: str = "index.html",
                 after_wav: Path | None = None) -> dict:
    """Apply edits to a temp copy, assert the fix, and compare axe violations before/after."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "site"; shutil.copytree(buggy_dir, work)
        try:
            apply_edits(work, edits)
        except PatchError as e:
            return {"passed": False, "reason": f"patch could not be applied: {e}", "checks": [], "new_violations": [], "after_announcement": ""}
        with a11y.serve_dir(buggy_dir) as base0, a11y.serve_dir(work) as base1, sync_playwright() as pw:
            br = pw.chromium.launch(**a11y.chromium_launch_kwargs())
            try:
                p0 = br.new_page(); p0.goto(base0 + entry); before = axe_counts(p0)
                p1 = br.new_page(); errs: list[str] = []
                p1.on("pageerror", lambda e: errs.append(str(e)))
                p1.goto(base1 + entry); p1.wait_for_timeout(150)
                after = axe_counts(p1)
                ok, reason, checks = check_finding(p1, issue_type, selector)
                nv = new_violations(before, after)
                if errs: ok, reason = False, f"patch introduced a JS error: {errs[0][:120]}"
                if ok and nv: ok, reason = False, f"patch introduced new axe violations: {nv}"
                ann = ""
                if ok and selector and issue_type not in ("tab_widget", "modal_dialog", "heading_skip"):
                    p2 = br.new_page(); p2.goto(base1 + entry)
                    h = p2.query_selector(selector)
                    if h:
                        ann = a11y.announcement(a11y.ax_info(p2, h))
                        if after_wav and ann: a11y.tts(ann, after_wav)
                return {"passed": ok, "reason": reason, "checks": checks, "new_violations": nv,
                        "axe_before": before, "axe_after": after, "after_announcement": ann}
            finally:
                br.close()
