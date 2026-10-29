"""Stage 2: Nemotron Super proposes minimal search/replace edits to the site source."""
from __future__ import annotations
import json
from pathlib import Path
from pydantic import ValidationError
from ..llm import first_json
from ..schemas import PatchResult

SYSTEM = """You fix web accessibility bugs with MINIMAL source edits.
Return STRICT JSON only: {"edits":[{"file":"index.html","old_str":"...","new_str":"..."}],"rationale":"one or two sentences"}
Rules: old_str must be copied from the file character for character and occur exactly once (include enough
surrounding text to be unique). Never shorten it with "..." or paraphrase it: an edit that does not match is discarded.
Prefer native HTML semantics, then ARIA; keep visible text unchanged; do not touch unrelated code; one edit per element.
State that changes when the user acts (aria-selected, aria-checked, aria-expanded, moving focus into a dialog) is set in
the site's JavaScript: edit the .js file's event handlers as well as the HTML."""

TEXT_EXT = {".html", ".js", ".css"}


def read_site(site_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(site_dir.iterdir()) if p.suffix in TEXT_EXT and p.name != "style.css"}


def build_prompt(finding, step: dict | None, files: dict[str, str], snippets: list[dict], failure: str = "", prior: dict | None = None) -> list[dict]:
    src = "\n\n".join(f"=== {n} ===\n{t}" for n, t in files.items())
    ctx = json.dumps({k: step.get(k) for k in ("selector", "html", "name", "role", "announcement")}, indent=1) if step else "{}"
    refs = "\n".join(f"- {s['title']} ({s['url']}): {s['content'][:300]}" for s in snippets)
    u = (f"Finding:\n{finding.model_dump_json(indent=1)}\n\nDOM context of the affected step:\n{ctx}\n\n"
         f"Grounding references (from live web search):\n{refs}\n\nSite source files:\n{src}\n\nReturn the JSON edits.")
    if failure:
        u += f"\n\nYour previous edits FAILED verification: {failure}\nPrevious edits: {json.dumps(prior)}\nFix it."
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": u}]


def parse_patch(raw: str) -> PatchResult:
    obj = first_json(raw)
    if isinstance(obj, list): obj = {"edits": obj}
    return PatchResult.model_validate(obj)


def propose(llm, role: str, finding, step, files, snippets, failure="", prior=None) -> PatchResult:
    msgs = build_prompt(finding, step, files, snippets, failure, prior)
    err = ""
    for _ in range(2):
        raw = llm.chat("patch" if role == "patch" else "escalation", role,
                       msgs if not err else msgs + [{"role": "user", "content": f"Invalid JSON ({err}). Return only the JSON."}], max_tokens=3000)
        try: return parse_patch(raw)
        except (ValueError, ValidationError, json.JSONDecodeError) as e: err = str(e)[:160]
    raise RuntimeError(f"patch model returned invalid JSON twice: {err}")


class PatchError(Exception):
    pass


def apply_edits(files_dir: Path, edits) -> None:
    """Apply search/replace edits in place. `file` may be a nested path under files_dir, never outside it.
    Fails cleanly (no partial writes) unless every old_str is unique."""
    staged: dict[str, str] = {}
    for e in edits:
        p = files_dir / e.file
        if not p.is_file() or not p.resolve().is_relative_to(files_dir.resolve()):
            raise PatchError(f"file not found: {e.file}")
        text = staged.get(e.file, p.read_text())
        n = text.count(e.old_str)
        if not e.old_str: raise PatchError("empty old_str")
        if n != 1: raise PatchError(f"old_str must match exactly once in {e.file} (matched {n}): {e.old_str[:60]!r}")
        staged[e.file] = text.replace(e.old_str, e.new_str)
    for f, t in staged.items(): (files_dir / f).write_text(t)
