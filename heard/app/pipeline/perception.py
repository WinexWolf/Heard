"""Stage 1: perception. Nemotron Omni listens to / watches the session and reports mismatches."""
from __future__ import annotations
import base64, json, re, subprocess, tempfile
from pathlib import Path
from pydantic import ValidationError
from ..llm import first_json
from ..schemas import FindingList, Finding

SYSTEM = """You are an accessibility auditor who evaluates what a screen-reader user HEARD against what was on screen.
Rules:
- Report ONLY issues supported by evidence in the session. Do not invent problems.
- Quote announced_text EXACTLY as it appears in the speech log (use "" when the user heard silence after an action).
- A control announced as just its role ("button"), a role that misleads ("clickable" for something that acts as a button/tab/checkbox),
  identical repeated announcements, headings that skip levels, missing state, or a visible change that was never announced are typical issues.
- issue_type MUST be the most specific type that fits. Each type decides how the fix is verified, so a wrong or vague type
  lets a bad fix pass. Pick by the symptom:
    missing_name        a control announced as only its role ("button", "link"), with no name
    missing_alt         an image announced as just "graphic"/"image", or not at all
    missing_label       a form field whose name comes only from its placeholder, or that has no name
    vague_link          links whose text alone is meaningless ("Learn more", "Click here", "Read more")
    repeated_control    several controls announced identically ("Edit, button" x5) that do different things
    error_not_announced an error, status or confirmation MESSAGE appears on screen but nothing (or "(silence)") is heard.
                        Not for new content shown by switching a tab (tab_widget) or opening a dialog (modal_dialog).
    label_in_name       the announced name differs from the visible label (heard "Continue", screen says "Create account")
    missing_state       a checkbox, switch or toggle with no checked/pressed/expanded state, or a state that never changes
    div_button          something that acts as a button is announced as "clickable", "group" or plain text
    modal_dialog        a dialog opens but is not announced as a dialog, or focus does not move into it
    tab_widget          tabs announced as "clickable" or plain text, with no "tab"/"selected"
    heading_skip        heading levels jump (level 1 straight to level 3)
  "clickable" is never a reason for other: decide whether the element acts as a button (div_button), a tab (tab_widget)
  or a checkbox (missing_state). Use other ONLY when none of the twelve types fits, and then say in evidence why none fits.
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


def audio_variant(caps: dict) -> str | None:
    """How the perception model accepts audio, as found by scripts/probe_models.py (None if it doesn't)."""
    return (caps.get("tests", {}).get("audio", {}) or {}).get("working_variant")


def request_extra(mode: str, caps: dict) -> dict | None:
    """Extra request body for perception: the video's own soundtrack is only used when asked for."""
    if mode == "native_av" and audio_variant(caps) == "video_audio_track":
        return {"mm_processor_kwargs": {"use_audio_in_video": True}}
    return None


def build_messages(session_dir: Path, steps: list[dict], mode: str, caps: dict) -> list[dict]:
    log = (session_dir / "speech_log.json").read_text() if (session_dir / "speech_log.json").exists() else "[]"
    text = (f"Session recorded with a SIMULATED screen reader. Speech log (what the user heard):\n{log}\n\n"
            f"Step-by-step (t = seconds into the recording):\n{step_table(steps)}\n\nReturn the JSON findings.")
    content: list[dict] = [{"type": "text", "text": text}]
    if mode == "native_av":
        video = session_dir / "session.mp4"
        b64 = base64.b64encode(video.read_bytes()).decode()
        content.append({"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}})
        wv = audio_variant(caps)
        if wv:
            content[0]["text"] = "The attached recording includes the screen reader's audio: listen to it as well as watching the screen.\n\n" + text
        if wv in ("input_audio_wav_b64", "audio_url_data_uri"):
            a = base64.b64encode((session_dir / "audio.wav").read_bytes()).decode()
            content.append({"type": "input_audio", "input_audio": {"data": a, "format": "wav"}} if wv == "input_audio_wav_b64"
                           else {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{a}"}})
    elif mode == "frames_plus_log" and (session_dir / "session.mp4").exists():
        for jpg in extract_frames(session_dir / "session.mp4", [s["t"] for s in steps]):
            content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}})
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


def parse_findings(raw: str) -> FindingList:
    return FindingList.model_validate(first_json(raw, "{"))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


SILENCE = {"", "silence", "no announcement", "nothing"}   # compared after norm(), so "(silence)" counts too


def evidence_check(findings: list[Finding], speech_log: list[dict], steps: list[dict], window: float = 3.0):
    """Deterministic grounding: keep a finding only if what it quotes was really said (or really silent) near t_start.
    A quote may span up to three consecutive announcements (e.g. a heading pair quoted together)."""
    supported, rejected = [], []
    for f in findings:
        log = sorted(speech_log, key=lambda e: e["t"])
        texts = [norm(e["text"]) for e in log]
        # a span qualifies if any announcement in it is near t_start; the span itself may run past the window
        spans = [" ".join(texts[i:j]) for i in range(len(log)) for j in range(i + 1, min(i + 4, len(log) + 1))
                 if any(abs(e["t"] - f.t_start) <= window for e in log[i:j])]
        quote = norm(f.announced_text)
        if quote not in SILENCE:
            ok = any(quote in s for s in spans)
            reason = "" if ok else f'announced_text "{f.announced_text}" not found in speech log within {window}s of t={f.t_start}'
        else:
            silent = [s for s in steps if s.get("silent") and abs(s["t"] - f.t_start) <= window]
            ok = bool(silent)
            reason = "" if ok else "claimed silence, but the log has speech / no silent action near that time"
        (supported if ok else rejected).append((f, reason))
    return [f for f, _ in supported], [{"finding": f.model_dump(), "reason": r} for f, r in rejected]


def ask_findings(llm, msgs: list[dict], extra: dict | None = None) -> FindingList:
    """One perception call, with one retry if the reply is not valid findings JSON."""
    err = ""
    for attempt in range(2):
        m = msgs if not err else msgs + [{"role": "user", "content": f"Your previous reply was invalid ({err}). Return ONLY valid JSON matching the schema."}]
        raw = llm.chat("perception", "perception", m, max_tokens=4096, temperature=0, extra=extra)
        try:
            return parse_findings(raw)
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            err = str(e)[:200]
    raise RuntimeError(f"perception returned invalid JSON twice: {err}")


def run_perception(llm, session_dir: Path, caps: dict):
    steps = json.loads((session_dir / "steps.json").read_text())
    log = json.loads((session_dir / "speech_log.json").read_text())
    mode = caps.get("PERCEPTION_MODE", "text_only_log")
    fl = ask_findings(llm, build_messages(session_dir, steps, mode, caps), request_extra(mode, caps))
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
