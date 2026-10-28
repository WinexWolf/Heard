"""Compare two speech snapshots: which announcements a code change added, removed or altered, page by page."""
from __future__ import annotations
from difflib import SequenceMatcher


def signature(step: dict) -> tuple:
    """What the user experiences at a step. Selectors and markup are left out on purpose: a refactor that changes
    them but not what is heard is not an accessibility change."""
    return (step["kind"], step["key"] if step["kind"] == "action" else "", step["announcement"])


def change_notes(base: list[dict] | None, head: list[dict]) -> dict[int, str]:
    """Map head step index -> how it changed. Removed steps are attached to the step now in their place, because an
    element that drops out of the tab order (a <button> that became a <div>) is often the regression itself."""
    if base is None:
        return {s["i"]: "(new page)" for s in head}
    notes: dict[int, str] = {}
    sm = SequenceMatcher(None, [signature(s) for s in base], [signature(s) for s in head], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        before = [base[i]["announcement"] or "(silence)" for i in range(i1, i2)]
        if op == "replace":
            for k, j in enumerate(range(j1, j2)):
                notes[j] = f'previously_heard="{before[k]}"' if k < len(before) else "(new step)"
            if len(before) > j2 - j1:
                notes[j2 - 1] += f' then_no_longer_heard="{" / ".join(before[j2 - j1:])}"'
        elif op == "insert":
            for j in range(j1, j2):
                notes[j] = "(new step)"
        elif op == "delete" and head:
            j = min(j1, len(head) - 1)
            notes[j] = (notes.get(j, "") + f' no_longer_heard_here="{" / ".join(before)}"').strip()
    return notes


def diff(base: dict | None, head: dict) -> dict[str, dict]:
    """Per page: {"status": new|changed|same, "notes": {...}, "lines": [(before, after), ...]} plus removed pages."""
    bp = (base or {}).get("pages", {})
    out: dict[str, dict] = {}
    for key, steps in head["pages"].items():
        notes = change_notes(bp.get(key), steps)
        status = "new" if key not in bp else ("changed" if notes else "same")
        lines = []
        if key in bp and notes:
            sm = SequenceMatcher(None, [signature(s) for s in bp[key]], [signature(s) for s in steps], autojunk=False)
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op != "equal":
                    lines.append((" / ".join(s["announcement"] or "(silence)" for s in bp[key][i1:i2]),
                                  " / ".join(s["announcement"] or "(silence)" for s in steps[j1:j2])))
        out[key] = {"status": status, "notes": notes, "lines": lines}
    for key in bp:
        if key not in head["pages"]:
            out[key] = {"status": "removed", "notes": {}, "lines": []}
    return out
