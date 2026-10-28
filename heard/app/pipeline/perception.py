"""Stage 1: perception. Nemotron Omni listens to / watches the session and reports mismatches."""
from __future__ import annotations
import base64, json, re, subprocess, tempfile
from pathlib import Path
from pydantic import ValidationError
from ..schemas import FindingList, Finding

SYSTEM = """You are an accessibility auditor who evaluates what a screen-reader user HEARD against what was on screen.
Rules:
- Report ONLY issues supported by evidence in the session. Do not invent problems.
- Quote announced_text EXACTLY as it appears in the speech log (use "" when the user heard silence after an action).
- A control announced as just its role ("button"), a role that misleads ("clickable" for something that acts as a button/tab/checkbox),
  identical repeated announcements, headings that skip levels, missing state, or a visible change that was never announced are typical issues.
- issue_type must be one of: missing_name, missing_alt, missing_label, vague_link, repeated_control, error_not_announced,
  label_in_name, missing_state, div_button, modal_dialog, tab_widget, heading_skip, other.
- severity: low|medium|high|critical. wcag_guess like "4.1.2" (criterion number only).
Return STRICT JSON only, no prose: {"findings":[{"id":"F1","t_start":0.0,"t_end":0.0,"announced_text":"","visible_text_or_description":"","issue_type":"","severity":"","wcag_guess":"","evidence":""}]}"""


def step_table(steps: list[dict]) -> str:
    rows = []
    for s in steps:
        heard = s["announcement"] if s["announcement"] else "(silence)"
        row = f't={s["t"]:.2f}s key={s["key"]} heard="{heard}" focused_visible_text="{s.get("visible_text","")[:60]}"'
        if s.get("screen_change"): row += f' screen_change="{s["screen_change"]}"'
        rows.append(row)
    return "\n".join(rows)


def extract_frames(video: Path, times: list[float], max_frames: int = 16) -> list[bytes]:
    out = []
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate(times[:max_frames]):
            f = Path(td) / f"{i}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t+0.4:.2f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=640:-2", str(f)], check=True)
            out.append(f.read_bytes())
    return out


def build_messages(session_dir: Path, steps: list[dict], mode: str, caps: dict) -> list[dict]:
    log = (session_dir / "speech_log.json").read_text() if (session_dir / "speech_log.json").exists() else "[]"
    text = (f"Session recorded with a SIMULATED screen reader. Speech log (what the user heard):\n{log}\n\n"
            f"Step-by-step (t = seconds into the recording):\n{step_table(steps)}\n\nReturn the JSON findings.")
    content: list[dict] = [{"type": "text", "text": text}]
    if mode == "native_av":
        video = session_dir / "session.mp4"
        b64 = base64.b64encode(video.read_bytes()).decode()
        content.append({"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}})
        wv = (caps.get("tests", {}).get("audio", {}) or {}).get("working_variant")
        if wv == "input_audio_wav_b64":
            a = base64.b64encode((session_dir / "audio.wav").read_bytes()).decode()
            content.append({"type": "input_audio", "input_audio": {"data": a, "format": "wav"}})
    elif mode == "frames_plus_log" and (session_dir / "session.mp4").exists():
        for jpg in extract_frames(session_dir / "session.mp4", [s["t"] for s in steps]):
            content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}})
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


def parse_findings(raw: str) -> FindingList:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return FindingList.model_validate(json.loads(m.group(0)))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def evidence_check(findings: list[Finding], speech_log: list[dict], steps: list[dict], window: float = 3.0):
    """Deterministic grounding: keep a finding only if what it quotes was really said (or really silent) near t_start."""
    supported, rejected = [], []
    for f in findings:
        near = [e for e in speech_log if abs(e["t"] - f.t_start) <= window]
        quote = norm(f.announced_text)
        if quote:
            ok = any(quote == norm(e["text"]) or quote in norm(e["text"]) for e in near)
            reason = "" if ok else f'announced_text "{f.announced_text}" not found in speech log within {window}s of t={f.t_start}'
        else:
            silent = [s for s in steps if s.get("silent") and abs(s["t"] - f.t_start) <= window]
            ok = bool(silent)
            reason = "" if ok else "claimed silence, but the log has speech / no silent action near that time"
        (supported if ok else rejected).append((f, reason))
    return [f for f, _ in supported], [{"finding": f.model_dump(), "reason": r} for f, r in rejected]


def ask_findings(llm, msgs: list[dict]) -> FindingList:
    """One perception call, with one retry if the reply is not valid findings JSON."""
    err = ""
    for attempt in range(2):
        m = msgs if not err else msgs + [{"role": "user", "content": f"Your previous reply was invalid ({err}). Return ONLY valid JSON matching the schema."}]
        raw = llm.chat("perception", "perception", m, max_tokens=4096)
        try:
            return parse_findings(raw)
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            err = str(e)[:200]
    raise RuntimeError(f"perception returned invalid JSON twice: {err}")


def run_perception(llm, session_dir: Path, caps: dict):
    steps = json.loads((session_dir / "steps.json").read_text())
    log = json.loads((session_dir / "speech_log.json").read_text())
    mode = caps.get("PERCEPTION_MODE", "text_only_log")
    fl = ask_findings(llm, build_messages(session_dir, steps, mode, caps))
    supported, rejected = evidence_check(fl.findings, log, steps)
    return {"mode": mode, "supported": supported, "rejected": rejected, "raw_count": len(fl.findings)}


def changes_prompt(steps: list[dict], notes: dict[int, str], context: int = 2) -> str:
    """Step table limited to changed steps (marked CHANGED with what changed) plus `context` neighbours each side."""
    keep = sorted({j for i in notes for j in range(max(0, i - context), min(len(steps), i + context + 1))})
    rows = [step_table([steps[j]]) + (f' CHANGED {notes[j]}' if j in notes else "") for j in keep]
    return ("A code change altered what a screen-reader user hears on this page. Steps marked CHANGED differ from the last "
            "accepted version; the other steps are unchanged context. Report only issues in, or caused by, the CHANGED steps.\n\n"
            "Step-by-step (t = step number):\n" + "\n".join(rows) + "\n\nReturn the JSON findings.")


def run_on_changes(llm, steps: list[dict], notes: dict[int, str]):
    """Audit only what a push changed. `notes` maps a step index to how it changed (see speechdiff.change_notes)."""
    fl = ask_findings(llm, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": changes_prompt(steps, notes)}])
    log = [{"t": s["t"], "text": s["announcement"]} for s in steps if s["announcement"]]
    supported, rejected = evidence_check(fl.findings, log, steps)
    return {"supported": supported, "rejected": rejected, "raw_count": len(fl.findings)}
