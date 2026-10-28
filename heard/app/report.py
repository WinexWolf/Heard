"""Render a `heard check` report into the self-contained HTML page built from frontend/src/Report.tsx."""
from __future__ import annotations
import json
from pathlib import Path

TEMPLATE = Path(__file__).parent / "report_ui" / "report.html"
PLACEHOLDER = "__HEARD_REPORT__"


def render(report: dict) -> str:
    if not TEMPLATE.exists():
        raise RuntimeError(f"{TEMPLATE} is missing: build it with `cd frontend && npm run build`")
    data = json.dumps(report).replace("</", "<\\/")      # cannot close the <script> it sits in
    return TEMPLATE.read_text().replace(PLACEHOLDER, data, 1)


def write(report: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(report))
    return path
