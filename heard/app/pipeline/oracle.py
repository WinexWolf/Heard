"""NON-MODEL placeholder ("oracle stub") used ONLY so the demo/UI/verifier work without API keys.

It maps each seeded bug to its session step and replays the human-written reference fix as the patch.
Results carry source="oracle_stub" and the UI labels them. They are NOT measurements of Heard's models;
real numbers come from `scripts/precompute_cache.py` / `eval/run_eval.py` run with live keys.
"""
from __future__ import annotations
import importlib.util, json
from pathlib import Path
from ..config import ROOT
from ..schemas import Edit, Finding

_spec = importlib.util.spec_from_file_location("build_demo_sites", ROOT / "scripts" / "build_demo_sites.py")
_mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)  # type: ignore
EDITS = _mod.EDITS

# (file) -> bug id -> indices into EDITS[site][file]
BUG_EDIT_IDX = {
    "shop": {"index.html": {"B01": [0], "B02": [1], "B04": [2, 3, 4], "B10": [5, 6, 7, 8, 9]}},
    "signup": {"index.html": {"B03": [0], "B06": [1], "B11": [2, 3], "B09": [4]}, "app.js": {"B11": [0]}},
    "dashboard": {"index.html": {"B05": [0], "B12": [1, 2], "B08": [3, 4, 5, 6, 7, 8, 9], "B07": [10]},
                  "app.js": {"B08": [0, 1], "B07": [2, 3]}},
}
# step predicate per bug (matched on the generated steps.json)
STEP_FOR = {
    "B01": lambda s: s["announcement"] == "button" and s["kind"] == "focus",
    "B02": lambda s: s["kind"] == "browse" and s["announcement"] in ("graphic", "image"),
    "B04": lambda s: s["announcement"] == "Learn more, link",
    "B10": lambda s: s["announcement"] == "Edit, button",
    "B03": lambda s: s["announcement"] == "Email address, edit text",
    "B06": lambda s: s["kind"] == "action" and "Enter a valid email" in s.get("screen_change", ""),
    "B09": lambda s: s["announcement"] == "Continue, button",
    "B11": lambda s: s["announcement"].startswith("I agree to the terms") and s["kind"] == "focus",
    "B05": lambda s: s["announcement"] == "Export CSV, clickable",
    "B07": lambda s: s["kind"] == "action" and "modal" in s.get("screen_change", ""),
    "B08": lambda s: s["announcement"] == "Overview, clickable",
    "B12": lambda s: s["announcement"].startswith("Overview, heading level 3"),
}
WCAG = {"missing_name": "4.1.2", "missing_alt": "1.1.1", "missing_label": "1.3.1", "vague_link": "2.4.4",
        "repeated_control": "2.4.6", "error_not_announced": "4.1.3", "label_in_name": "2.5.3",
        "missing_state": "4.1.2", "div_button": "4.1.2", "modal_dialog": "4.1.2", "tab_widget": "4.1.2", "heading_skip": "1.3.1"}
STATIC_CITATIONS = {
    "4.1.2": ("Understanding SC 4.1.2: Name, Role, Value", "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html"),
    "1.1.1": ("Understanding SC 1.1.1: Non-text Content", "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html"),
    "1.3.1": ("Understanding SC 1.3.1: Info and Relationships", "https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html"),
    "2.4.4": ("Understanding SC 2.4.4: Link Purpose (In Context)", "https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html"),
    "2.4.6": ("Understanding SC 2.4.6: Headings and Labels", "https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels.html"),
    "4.1.3": ("Understanding SC 4.1.3: Status Messages", "https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html"),
    "2.5.3": ("Understanding SC 2.5.3: Label in Name", "https://www.w3.org/WAI/WCAG22/Understanding/label-in-name.html"),
}


def oracle_findings(site: str, steps: list[dict]):
    bugs = json.loads((ROOT / "data" / "bugs" / f"{site}.json").read_text())
    out = []
    for b in bugs:
        step = next((s for s in steps if STEP_FOR[b["id"]](s)), None)
        if not step: continue
        f = Finding(id=f"O-{b['id']}", t_start=step["t"], t_end=step["t"] + 1.5, announced_text=step["announcement"],
                    visible_text_or_description=b["description"], issue_type=b["category"] if b["category"] in WCAG else "other",
                    severity="high", wcag_guess=WCAG.get(b["category"], "4.1.2"), evidence="oracle stub (reference mapping)")
        out.append((b, step, f))
    return out


def oracle_edits(site: str, bug_id: str) -> list[Edit]:
    edits = []
    for fname, mapping in BUG_EDIT_IDX[site].items():
        for i in mapping.get(bug_id, []):
            old, new = EDITS[site][fname][i]
            edits.append(Edit(file=fname, old_str=old, new_str=new))
    return edits
