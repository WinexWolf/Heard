"""heard fix: patch the source for regressions `heard check` found, keeping only fixes verified on the running app.

Per finding: locate the source file(s) from the element's markup and text, ask the patch model for minimal
search/replace edits, write them to the working tree, and let the dev server reload. The live page must then pass
the assertion for the issue type with no new axe violations. A failed attempt is restored byte for byte and retried
once with the failure reason, then escalated once. Nothing unverified is left behind.
"""
from __future__ import annotations
import difflib, re, time
from pathlib import Path
from playwright.sync_api import Browser
from . import a11y
from .pipeline import citation, patch as patchmod, verify
from .schemas import Finding

SOURCE_EXT = {".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".astro", ".mdx"}
SKIP_DIRS = {"node_modules", ".git", ".heard", "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", ".venv", "coverage"}
MAX_BYTES = 60_000
ATTR = re.compile(r'([\w:-]+)="([^"]*)"')
WEIGHT = {"id": 5, "data-testid": 5, "aria-label": 4, "alt": 4, "placeholder": 3, "name": 2, "href": 2}


def clues(step: dict) -> list[tuple[str, int]]:
    """Strings likely to appear verbatim in the element's source, with how specific each one is."""
    out: dict[str, int] = {}
    for k, v in ATTR.findall(step.get("html") or ""):
        if k == "class":
            for c in v.split():
                if len(c) > 2: out[c] = max(out.get(c, 0), 1)
        elif k in WEIGHT and v.strip():
            out[v] = max(out.get(v, 0), WEIGHT[k])
    for text in (step.get("visible_text"), step.get("name")):
        t = (text or "").strip()
        if len(t) >= 3: out[t[:60]] = max(out.get(t[:60], 0), 3)
    return list(out.items())


def source_files(root: Path, dirs: list[str]):
    for d in dirs:
        base = (root / d).resolve()
        for f in sorted(base.rglob("*")) if base.is_dir() else []:
            if f.suffix in SOURCE_EXT and f.is_file() and not SKIP_DIRS.intersection(f.relative_to(base).parts) and f.stat().st_size <= MAX_BYTES:
                yield f


def locate(root: Path, dirs: list[str], step: dict, k: int = 3) -> dict[str, str]:
    """Top-k source files by how many of the element's clues they contain, keyed by path relative to root."""
    cl, scored = clues(step), []
    for f in source_files(root, dirs):
        text = f.read_text(errors="ignore")
        score = sum(w for c, w in cl if c in text)
        if score: scored.append((score, f, text))
    scored.sort(key=lambda x: -x[0])
    return {f.relative_to(root.resolve()).as_posix(): text for _, f, text in scored[:k]}


def page_url(cfg: dict, key: str) -> str:
    path = cfg["flows"][key.split(":", 1)[1]].get("page", "/") if key.startswith("flow:") else key
    return cfg["url"].rstrip("/") + path


def axe_on(browser: Browser, url: str) -> dict[str, int]:
    p = browser.new_page()
    try:
        p.goto(url, wait_until="networkidle"); return verify.axe_counts(p)
    finally:
        p.close()


def check_live(browser: Browser, url: str, issue_type: str, selector: str, axe_before: dict | None, timeout: float) -> dict:
    """Poll the running app until the assertion passes or `timeout` runs out (dev servers take a moment to reload)."""
    deadline = time.time() + timeout
    while True:
        p = browser.new_page()
        try:
            p.goto(url, wait_until="networkidle")
            ok, reason, checks = verify.check_finding(p, issue_type, selector)
        finally:
            p.close()
        if ok or time.time() >= deadline:
            break
        time.sleep(0.5)
    nv = verify.new_violations(axe_before, axe_on(browser, url)) if ok and axe_before is not None else []
    if nv: ok, reason = False, f"patch introduced new axe violations: {nv}"
    ann = ""
    if ok and selector:
        p = browser.new_page()
        try:
            p.goto(url, wait_until="networkidle"); h = p.query_selector(selector)
            ann = a11y.announcement(a11y.ax_info(p, h)) if h else ""
        finally:
            p.close()
    return {"passed": ok, "reason": reason, "checks": checks, "new_violations": nv, "after_announcement": ann}


def unified(path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{path}", f"b/{path}"))


def fix_finding(llm, models: dict, cfg: dict, root: Path, browser: Browser, finding: dict, step: dict,
                snippets: list[dict], keep: bool) -> dict:
    f = Finding.model_validate({k: finding[k] for k in Finding.model_fields})
    url, sel, timeout = page_url(cfg, finding["page"]), step.get("selector") or "", cfg["fix_timeout"]
    pre = check_live(browser, url, f.issue_type, sel, None, 0)
    if pre["passed"]:
        return {"status": "already_fixed", "attempts": [], "reason": "the live page already passes this check"}
    files = locate(root, cfg["src"], step)
    if not files:
        return {"status": "no_source", "attempts": [], "reason": f"no file under {cfg['src']} contains this element's text or attributes"}
    axe_before = axe_on(browser, url)
    roles = ["patch", "patch"] + (["escalation"] if models.get("escalation") else [])
    attempts, failure, prior = [], "", None
    for role in roles:
        try:
            res = patchmod.propose(llm, role, f, step, files, snippets, failure, prior)
        except Exception as e:
            attempts.append({"model": models.get(role), "role": role, "passed": False, "reason": f"model error: {e}", "edits": []})
            failure, prior = str(e), None; continue
        edits = [e.model_dump() for e in res.edits]
        backups = {e.file: (root / e.file).read_text() for e in res.edits if (root / e.file).is_file()}
        try:
            patchmod.apply_edits(root, res.edits)
            v = check_live(browser, url, f.issue_type, sel, axe_before, timeout)
        except patchmod.PatchError as e:
            v = {"passed": False, "reason": f"patch could not be applied: {e}", "checks": []}
        except BaseException:
            restore(root, backups); raise
        attempts.append({"model": models.get(role), "role": role, "passed": v["passed"], "reason": v["reason"], "edits": edits,
                         "rationale": res.rationale, "verification": v})
        if v["passed"]:
            diff = "".join(unified(p, old, (root / p).read_text()) for p, old in backups.items())
            if not keep: restore(root, backups)
            return {"status": "fixed", "kept": keep, "model": models.get(role), "attempts": attempts, "files": sorted(backups),
                    "diff": diff, "rationale": res.rationale, "after_announcement": v["after_announcement"]}
        restore(root, backups)
        failure, prior = v["reason"], edits
    return {"status": "failed", "attempts": attempts, "reason": failure}


def restore(root: Path, backups: dict[str, str]) -> None:
    for p, text in backups.items():
        (root / p).write_text(text)


def run_fix(cfg: dict, rep: dict, snap: dict, llm, models: dict, root: Path, browser: Browser,
            everything: bool = False, keep: bool = True, tavily_key: str | None = None) -> list[dict]:
    """Fix the report's failing findings (or all with `everything`). Adds a "fix" entry to each finding it touches."""
    from .cli import SEVERITY
    targets = [f for f in rep["findings"] if everything or SEVERITY.index(f["severity"]) >= SEVERITY.index(cfg["fail_on"])]
    results = []
    for f in targets:
        steps = snap["pages"][f["page"]]
        step = steps[min(int(f["t_start"]), len(steps) - 1)]
        f["wcag_guess"] = citation.criterion(f["issue_type"], f["wcag_guess"])
        snippets = []
        if tavily_key:
            try:
                _, snippets = citation.search(llm.tracker, tavily_key, citation.build_query(f["issue_type"], f["wcag_guess"]))
            except Exception:
                snippets = []
        f["fix"] = fix_finding(llm, models, cfg, root, browser, f, step, snippets, keep)
        results.append(f)
    return results
