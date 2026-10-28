"""heard: catch accessibility regressions on every push.

  heard init                 write heard.toml
  heard snapshot             record what a screen-reader user hears now -> heard.snapshot.json
  heard check                re-record, diff against the base snapshot, audit only what changed, exit 1 on regressions

Every push is re-recorded (cheap, deterministic, no model). The model only sees steps whose announcements changed,
and identical diffs are answered from .heard/cache.json, so a push that changes nothing users hear costs no tokens.
"""
from __future__ import annotations
import argparse, hashlib, json, os, signal, subprocess, sys, time, tomllib
from contextlib import contextmanager
from pathlib import Path
import httpx
from dotenv import load_dotenv
from . import driver, speechdiff
from .pipeline import perception

SEVERITY = ["low", "medium", "high", "critical"]
DEFAULTS = {"pages": ["/"], "flows": {}, "snapshot": "heard.snapshot.json", "fail_on": "medium", "start_timeout": 90, "out_dir": ".heard"}
TEMPLATE = '''# Heard: accessibility regression checks. Docs: https://github.com/WinexWolf/Heard
url = "{url}"
# start = "npm run dev"          # optional: Heard starts the app and waits for the URL
pages = ["/"]
snapshot = "heard.snapshot.json"  # commit this: PRs then show what screen-reader users will hear differently
fail_on = "medium"                # fail the check on new issues at or above this severity

# Heard only presses Tab on its own. Declare flows for anything that needs Enter, Space or typing.
# [flows.signup-error]
# page = "/signup"
# steps = ["tab", "tab", {{ type = "not-an-email" }}, "tab", "enter"]
'''


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"{path} not found: run `heard init` first")
    cfg = {**DEFAULTS, **tomllib.loads(path.read_text())}
    if "url" not in cfg:
        raise SystemExit(f"{path}: `url` is required")
    if cfg["fail_on"] not in SEVERITY:
        raise SystemExit(f"{path}: fail_on must be one of {SEVERITY}")
    return cfg


def _up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2).status_code < 500
    except httpx.HTTPError:
        return False


@contextmanager
def app_running(cfg: dict):
    """Use the app if it is already up; otherwise run `start` and wait for the URL."""
    if _up(cfg["url"]) or not cfg.get("start"):
        yield; return
    proc = subprocess.Popen(cfg["start"], shell=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + cfg["start_timeout"]
        while not _up(cfg["url"]):
            if proc.poll() is not None: raise SystemExit(f"`{cfg['start']}` exited with code {proc.returncode} before {cfg['url']} came up")
            if time.time() > deadline: raise SystemExit(f"{cfg['url']} did not come up within {cfg['start_timeout']}s")
            time.sleep(0.5)
        yield
    finally:
        try: os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError: pass


def record(cfg: dict) -> dict:
    with app_running(cfg):
        if not _up(cfg["url"]):
            raise SystemExit(f"{cfg['url']} is not reachable: start the app or set `start` in heard.toml")
        return driver.snapshot(cfg["url"], cfg["pages"], cfg["flows"])


def default_base_ref() -> str:
    """PRs compare against the target branch; local runs against the last commit."""
    return f"origin/{os.environ['GITHUB_BASE_REF']}" if os.getenv("GITHUB_BASE_REF") else "HEAD"


def load_baseline(path: Path, ref: str) -> tuple[dict | None, str]:
    r = subprocess.run(["git", "show", f"{ref}:./{path.as_posix()}"], capture_output=True, text=True)
    if r.returncode == 0:
        return json.loads(r.stdout), f"{ref}:{path}"
    if path.exists():
        return json.loads(path.read_text()), str(path)
    return None, "none"


def make_llm():
    from .config import get_settings
    from .llm import LLM
    s = get_settings()
    if any(not v or v.startswith("<") for v in (s.api_key, s.base_url, s.models["perception"])):
        return None
    return LLM(s)


def run_check(cfg: dict, base: dict | None, head: dict, llm=None, cache_path: Path | None = None) -> dict:
    """Diff head against base, audit changed steps (model calls only on cache misses), decide pass/fail."""
    changes = speechdiff.diff(base, head)
    cache = json.loads(cache_path.read_text()) if cache_path and cache_path.exists() else {}
    findings, rejected, audited, calls = [], [], True, 0
    for key, ch in changes.items():
        if not ch["notes"]:
            continue
        steps = head["pages"][key]
        prompt = perception.changes_prompt(steps, ch["notes"])
        h = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        if h not in cache:
            if llm is None:
                audited = False; continue
            res = perception.run_on_changes(llm, steps, ch["notes"]); calls += 1
            cache[h] = {"supported": [f.model_dump() for f in res["supported"]], "rejected": res["rejected"]}
        findings += [{"page": key, "step": steps[min(int(f["t_start"]), len(steps) - 1)]["announcement"], **f} for f in cache[h]["supported"]]
        rejected += [{"page": key, **r} for r in cache[h]["rejected"]]
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True); cache_path.write_text(json.dumps(cache, indent=1))
    worst = max((SEVERITY.index(f["severity"]) for f in findings), default=-1)
    failing = [f for f in findings if SEVERITY.index(f["severity"]) >= SEVERITY.index(cfg["fail_on"])]
    changed = sum(len(c["notes"]) for c in changes.values())
    result = "fail" if failing else ("unaudited" if changed and not audited else "pass")
    return {"result": result, "url": head["url"], "fail_on": cfg["fail_on"], "worst": SEVERITY[worst] if worst >= 0 else None,
            "pages": {k: {"status": c["status"], "changed_steps": len(c["notes"]), "lines": c["lines"]} for k, c in changes.items()},
            "changed_steps": changed, "findings": findings, "failing": len(failing), "rejected_unsupported": rejected,
            "model_calls": calls, "cost": llm.tracker.summary()["total"] if llm is not None and hasattr(llm, "tracker") else None}


def markdown(rep: dict, base_label: str) -> str:
    icon = {"pass": "✅", "fail": "❌", "unaudited": "⚠️"}[rep["result"]]
    head = {"pass": "No accessibility regressions", "fail": f"{rep['failing']} accessibility regression(s)",
            "unaudited": "Speech changed but was not audited (no model key configured)"}[rep["result"]]
    out = [f"## {icon} Heard: {head}", "",
           f"{len(rep['pages'])} page(s) scanned · {rep['changed_steps']} announcement(s) changed vs `{base_label}` · "
           f"{rep['model_calls']} model call(s)", ""]
    if rep["findings"]:
        out += ["| Page | Heard | Issue | Severity | WCAG |", "|---|---|---|---|---|"]
        out += [f"| `{f['page']}` | “{f['announced_text'] or 'silence'}” | {f['issue_type'].replace('_', ' ')}: {f['visible_text_or_description']} "
                f"| {f['severity']} | {f['wcag_guess']} |" for f in rep["findings"]]
        out.append("")
    lines = [(k, b, a) for k, p in rep["pages"].items() for b, a in p["lines"]]
    if lines:
        out += ["<details><summary>What screen-reader users will hear differently</summary>", ""]
        out += [f"- `{k}`: “{b or '—'}” → “{a or '—'}”" for k, b, a in lines]
        out += ["", "</details>"]
    return "\n".join(out) + "\n"


def cmd_init(a) -> int:
    p = Path(a.config)
    if p.exists():
        print(f"{p} already exists"); return 2
    p.write_text(TEMPLATE.format(url=a.url)); print(f"wrote {p}: set `url` and `pages`, then run `heard snapshot`")
    return 0


def cmd_snapshot(a) -> int:
    cfg = load_config(Path(a.config))
    snap = record(cfg)
    Path(cfg["snapshot"]).write_text(json.dumps(snap, indent=1))
    print(f"wrote {cfg['snapshot']}: {sum(len(s) for s in snap['pages'].values())} steps across {len(snap['pages'])} page(s)")
    return 0


def cmd_check(a) -> int:
    cfg = load_config(Path(a.config))
    base, base_label = load_baseline(Path(cfg["snapshot"]), a.base or default_base_ref())
    head = record(cfg)
    changed = any(c["notes"] for c in speechdiff.diff(base, head).values())
    llm = make_llm() if changed and not a.no_llm else None
    out = Path(cfg["out_dir"])
    rep = run_check(cfg, base, head, llm, out / "cache.json")
    md = markdown(rep, base_label)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=1)); (out / "report.md").write_text(md)
    (out / "snapshot.json").write_text(json.dumps(head, indent=1))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh: fh.write(md)
    if a.update:
        Path(cfg["snapshot"]).write_text(json.dumps(head, indent=1))
    print(md)
    return 1 if rep["result"] == "fail" else 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path.cwd() / ".env")
    ap = argparse.ArgumentParser(prog="heard", description="Catch accessibility regressions by listening to your app on every push.")
    ap.add_argument("-c", "--config", default="heard.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="write heard.toml"); p.add_argument("--url", default="http://localhost:5173"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("snapshot", help="record what users hear now and save it as the accepted baseline"); p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("check", help="diff against the base snapshot, audit changes, exit 1 on regressions")
    p.add_argument("--base", help="git ref holding the baseline snapshot (default: PR target branch in CI, else HEAD)")
    p.add_argument("--no-llm", action="store_true", help="only report what changed; spend no tokens")
    p.add_argument("--update", action="store_true", help="also save the new snapshot as the baseline")
    p.set_defaults(fn=cmd_check)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
