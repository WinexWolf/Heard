"""Orchestrator: perception -> (Tavily -> patch -> verify -> repair -> escalate) per finding."""
from __future__ import annotations
import json, shutil, time
from pathlib import Path
from typing import Callable
from ..config import ROOT, DATA, get_settings
from ..llm import LLM, CostTracker
from ..schemas import Finding
from . import perception, citation, patch as patchmod, verify, oracle

Emit = Callable[[dict], None]


def load_session(session_id: str) -> tuple[Path, dict, list[dict]]:
    d = DATA / "sessions" / session_id
    if not d.exists(): raise FileNotFoundError(session_id)
    meta = json.loads((d / "meta.json").read_text())
    return d, meta, json.loads((d / "steps.json").read_text())


def nearest_step(f: Finding, steps: list[dict]) -> dict | None:
    if not steps: return None
    exact = [s for s in steps if s["announcement"] and f.announced_text and s["announcement"].lower() == f.announced_text.lower()]
    pool = exact or steps
    return min(pool, key=lambda s: abs(s["t"] - f.t_start))


PAGE_LEVEL = {"tab_widget", "modal_dialog", "heading_skip"}   # verified on the whole widget/page: one fix covers every step
GROUPED = {"repeated_control", "vague_link"}                 # one fix covers the whole group of identical controls


def dedupe(findings: list[Finding], steps: list[dict]) -> tuple[list[Finding], list[dict]]:
    """Merge findings that one fix would cover (the same tab widget heard at three steps), so each is patched once."""
    kept, merged, seen = [], [], {}
    for f in findings:
        step = nearest_step(f, steps)
        sel = (step or {}).get("selector") or ""
        key = (f.issue_type,) if f.issue_type in PAGE_LEVEL else \
              (f.issue_type, verify.group_selector(sel)) if f.issue_type in GROUPED else (f.issue_type, sel or f.announced_text)
        if key in seen:
            merged.append({"finding": f.model_dump(), "duplicate_of": seen[key]})
        else:
            seen[key] = f.id; kept.append(f)
    return kept, merged


# Roles an issue type can apply to. A finding on any other role is mistyped, and its type picks the wrong check.
ROLES = {"vague_link": {"link"}, "missing_alt": {"img", "image"},
         "missing_label": {"textbox", "combobox", "searchbox", "spinbutton", "listbox"}}


def fit_type(f: Finding, step: dict | None) -> Finding:
    """Correct an issue type that cannot apply to the element. The one mismatch with a clear meaning: a named control
    whose name does not contain its visible text is a label_in_name bug (e.g. "Continue" on a "Create account" button)."""
    role = (step or {}).get("role", "")
    if f.issue_type not in ROLES or not role or role in ROLES[f.issue_type]:
        return f
    name, vis = (step.get("name") or "").strip().lower(), (step.get("visible_text") or "").strip().lower()
    if name and vis and vis not in name:
        f.evidence = f"{f.evidence} [type corrected: {f.issue_type} cannot apply to a {role}]".strip()
        f.issue_type = "label_in_name"
    return f


def not_reproduced(site_dir: Path, f: Finding, step: dict | None) -> str:
    """Reason the finding is not real, or "". If the unpatched page already passes the check for this issue type,
    there is nothing to fix (a real <button> reported as a fake one), and a "verified fix" would be meaningless."""
    v = verify.verify_edits(site_dir, [], f.issue_type, (step or {}).get("selector") or "")
    return "" if not v["passed"] else f"not reproduced: the unpatched page already passes the {f.issue_type} check"


def _site_dir(meta: dict) -> Path:
    return ROOT / meta["source_dir"]


def fix_one(llm, settings, tracker, f, step, site_dir, snippets, out_dir: Path, emit: Emit) -> dict:
    files = patchmod.read_site(site_dir)
    sel = step["selector"] if step else ""
    attempts, failure, prior = [], "", None
    for role in ("patch", "patch", "escalation"):
        if role == "escalation" and not settings.models["escalation"]:
            break
        try:
            res = patchmod.propose(llm, role, f, step, files, snippets, failure, prior)
        except Exception as e:
            attempts.append({"model": settings.models[role], "role": role, "passed": False, "reason": f"model error: {e}", "edits": []})
            failure, prior = str(e), None; continue
        emit({"stage": "patch", "finding": f.id, "role": role, "edits": [e.model_dump() for e in res.edits], "rationale": res.rationale})
        v = verify.verify_edits(site_dir, res.edits, f.issue_type, sel, after_wav=out_dir / f"after_{f.id}.wav")
        attempts.append({"model": settings.models[role], "role": role, "passed": v["passed"], "reason": v["reason"],
                         "edits": [e.model_dump() for e in res.edits], "rationale": res.rationale, "verification": v})
        emit({"stage": "verify", "finding": f.id, "passed": v["passed"], "reason": v["reason"], "role": role})
        if v["passed"]: break
        failure, prior = v["reason"], [e.model_dump() for e in res.edits]
    last = attempts[-1] if attempts else None
    return {"attempts": attempts, "fixed": bool(last and last["passed"]),
            "model_used": last["model"] if last and last["passed"] else None,
            "final": last}


def analyze_live(session_id: str, emit: Emit = lambda e: None, out_dir: Path | None = None) -> dict:
    s = get_settings()
    if not s.live_ready:
        raise RuntimeError("Live mode needs NEBIUS_API_KEY, NEBIUS_BASE_URL, TAVILY_API_KEY and the three MODEL_* ids in .env")
    tracker = CostTracker(s.prices); llm = LLM(s, tracker)
    d, meta, steps = load_session(session_id)
    out_dir = out_dir or DATA / "runs" / session_id; out_dir.mkdir(parents=True, exist_ok=True)
    caps = s.capabilities()
    emit({"stage": "perception", "status": "start", "mode": caps["PERCEPTION_MODE"], "model": s.models["perception"]})
    p = perception.run_perception(llm, d, caps)
    supported, merged = dedupe([fit_type(f, nearest_step(f, steps)) for f in p["supported"]], steps)
    emit({"stage": "findings", "supported": [f.model_dump() for f in supported], "rejected": p["rejected"], "merged": len(merged),
          "cost": tracker.summary()["total"]})
    results, rejected = [], list(p["rejected"])
    for f in supported:
        step = nearest_step(f, steps)
        if reason := not_reproduced(_site_dir(meta), f, step):
            rejected.append({"finding": f.model_dump(), "reason": reason})
            emit({"stage": "verify", "finding": f.id, "passed": False, "reason": reason, "role": "precheck"}); continue
        f.wcag_guess = citation.criterion(f.issue_type, f.wcag_guess)
        q = citation.build_query(f.issue_type, f.wcag_guess)
        try:
            cites, snippets = citation.search(tracker, s.tavily_key, q)
        except Exception as e:
            cites, snippets = [], []; emit({"stage": "citation", "finding": f.id, "error": str(e)})
        emit({"stage": "citation", "finding": f.id, "query": q, "citations": [c.model_dump() for c in cites]})
        fx = fix_one(llm, s, tracker, f, step, _site_dir(meta), snippets, out_dir, emit)
        results.append({"finding": f.model_dump(), "step": step, "citations": [c.model_dump() for c in cites], "query": q, **fx})
        emit({"stage": "cost", "cost": tracker.summary()["total"]})
    out = _package(session_id, meta, "live", caps["PERCEPTION_MODE"], results, rejected, p["raw_count"], tracker.summary(), s, out_dir)
    out["merged_duplicates"] = merged
    (out_dir / "result.json").write_text(json.dumps(out, indent=2))
    emit({"stage": "done", "result": out})
    return out


def analyze_oracle(session_id: str, emit: Emit = lambda e: None, out_dir: Path | None = None) -> dict:
    """Non-model placeholder run (see oracle.py). Labeled source='oracle_stub' everywhere."""
    d, meta, steps = load_session(session_id)
    out_dir = out_dir or DATA / "runs" / session_id; out_dir.mkdir(parents=True, exist_ok=True)
    tracker = CostTracker()
    results = []
    emit({"stage": "perception", "status": "start", "mode": "oracle_stub", "model": None})
    triples = oracle.oracle_findings(meta["site"], steps)
    emit({"stage": "findings", "supported": [f.model_dump() for _, _, f in triples], "rejected": [], "cost": tracker.summary()["total"]})
    for b, step, f in triples:
        title, url = oracle.STATIC_CITATIONS.get(f.wcag_guess, ("WCAG 2.2", "https://www.w3.org/TR/WCAG22/"))
        cites = [{"title": title, "url": url}]
        edits = oracle.oracle_edits(meta["site"], b["id"])
        emit({"stage": "citation", "finding": f.id, "query": "(static reference, not a live Tavily call)", "citations": cites})
        emit({"stage": "patch", "finding": f.id, "role": "oracle", "edits": [e.model_dump() for e in edits], "rationale": "Reference fix (human-written)."})
        v = verify.verify_edits(_site_dir(meta), edits, f.issue_type, step["selector"], after_wav=out_dir / f"after_{f.id}.wav")
        emit({"stage": "verify", "finding": f.id, "passed": v["passed"], "reason": v["reason"], "role": "oracle"})
        att = {"model": "oracle_stub", "role": "oracle", "passed": v["passed"], "reason": v["reason"],
               "edits": [e.model_dump() for e in edits], "rationale": "Reference fix (human-written).", "verification": v}
        results.append({"finding": f.model_dump(), "step": step, "citations": cites, "query": "static", "attempts": [att],
                        "fixed": v["passed"], "model_used": "oracle_stub" if v["passed"] else None, "final": att, "bug_id": b["id"]})
    out = _package(session_id, meta, "oracle_stub", "oracle_stub", results, [], len(results), tracker.summary(), get_settings(), out_dir)
    (out_dir / "result.json").write_text(json.dumps(out, indent=2))
    emit({"stage": "done", "result": out})
    return out


def _package(session_id, meta, source, mode, results, rejected, raw_count, cost, s, out_dir) -> dict:
    d = DATA / "sessions" / session_id
    for r in results:
        step = r.get("step")
        r["before_audio"] = f"sessions/{session_id}/step_{step['i']}_before.wav" if step and (d / f"step_{step['i']}_before.wav").exists() else None
        fid = r["finding"]["id"]
        r["after_audio"] = f"runs/{session_id}/after_{fid}.wav" if (out_dir / f"after_{fid}.wav").exists() else None
    return {"session_id": session_id, "site": meta["site"], "source": source, "perception_mode": mode,
            "models": s.models, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "label": meta.get("label"), "findings": results, "rejected_unsupported": rejected,
            "raw_finding_count": raw_count, "cost": cost}


def analyze(session_id: str, live: bool, emit: Emit = lambda e: None, out_dir: Path | None = None) -> dict:
    return analyze_live(session_id, emit, out_dir) if live else analyze_oracle(session_id, emit, out_dir)
