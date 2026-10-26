"""Milestone 0: capability probe.

Lists Token Factory models, finds Nemotron ones, and tests which input types the
perception model accepts (text / image / video / audio). Writes data/capabilities.json.
Never guesses: every variant tried is recorded with its raw outcome.
"""
from __future__ import annotations
import base64, json, os, subprocess, sys, tempfile, time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
OUT = ROOT / "data" / "capabilities.json"

BASE = os.getenv("NEBIUS_BASE_URL", "").split("#")[0].strip().rstrip("/")
KEY = os.getenv("NEBIUS_API_KEY", "")
MODEL = os.getenv("MODEL_PERCEPTION", "")


def _is_placeholder(v: str) -> bool:
    return not v or v.startswith("<")


def make_media(tmp: Path) -> dict[str, bytes]:
    """Tiny png / mp4 / wav generated with ffmpeg so the probe has no asset dependencies."""
    png, mp4, wav = tmp / "t.png", tmp / "t.mp4", tmp / "t.wav"
    run = lambda *a: subprocess.run(a, check=True, capture_output=True)
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x240:d=1", "-frames:v", "1", str(png))
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x240:d=2:r=5", "-pix_fmt", "yuv420p", str(mp4))
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-ar", "16000", "-ac", "1", str(wav))
    return {"png": png.read_bytes(), "mp4": mp4.read_bytes(), "wav": wav.read_bytes()}


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def chat(client: httpx.Client, content, max_tokens=64) -> tuple[bool, str]:
    body = {"model": MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}
    try:
        r = client.post(f"{BASE}/chat/completions", json=body, timeout=120)
    except Exception as e:  # network
        return False, f"exception: {e!r}"
    if r.status_code == 200:
        try:
            return True, r.json()["choices"][0]["message"].get("content") or ""
        except Exception as e:
            return False, f"bad 200 body: {e!r} {r.text[:300]}"
    return False, f"HTTP {r.status_code}: {r.text[:400]}"


def main() -> int:
    caps: dict = {"probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "base_url": BASE,
                  "nemotron_models": [], "perception_model": MODEL, "tests": {},
                  "PERCEPTION_MODE": "text_only_log"}
    if _is_placeholder(KEY) or _is_placeholder(BASE):
        caps["note"] = "NEBIUS_API_KEY / NEBIUS_BASE_URL not set; defaulted to text_only_log. Re-run with keys."
        OUT.write_text(json.dumps(caps, indent=2)); print(caps["note"]); return 1

    client = httpx.Client(headers={"Authorization": f"Bearer {KEY}"})
    r = client.get(f"{BASE}/models", timeout=60)
    if r.status_code != 200:
        caps["note"] = f"model list failed: HTTP {r.status_code} {r.text[:300]}"
        OUT.write_text(json.dumps(caps, indent=2)); print(caps["note"]); return 1
    ids = [m["id"] for m in r.json().get("data", [])]
    caps["nemotron_models"] = sorted(i for i in ids if "nemotron" in i.lower())
    print("Nemotron models:"); [print("  ", i) for i in caps["nemotron_models"]]

    if _is_placeholder(MODEL) or MODEL not in ids:
        caps["note"] = (f"MODEL_PERCEPTION={MODEL!r} is not in the model list. Pick an ID from "
                        "nemotron_models above (look for 'omni'), set it in .env, re-run.")
        OUT.write_text(json.dumps(caps, indent=2)); print(caps["note"]); return 1

    with tempfile.TemporaryDirectory() as td:
        m = make_media(Path(td))
    T = caps["tests"]
    ok, out = chat(client, "Reply with the single word: pong"); T["text"] = {"ok": ok, "detail": out[:200]}
    ok, out = chat(client, [{"type": "text", "text": "What colour is this image? One word."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64(m['png'])}"}}])
    T["image"] = {"ok": ok, "detail": out[:200]}

    # Video variants: record every one tried. Check current Nebius docs for the documented shape.
    vq = "Describe this video in one short sentence."
    video_variants = {
        "video_url_data_uri": [{"type": "text", "text": vq},
                               {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64(m['mp4'])}"}}],
    }
    T["video"] = {"ok": False, "variants": {}}
    for name, content in video_variants.items():
        ok, out = chat(client, content); T["video"]["variants"][name] = {"ok": ok, "detail": out[:300]}
        if ok: T["video"]["ok"] = True; T["video"]["working_variant"] = name; break

    aq = "What do you hear? One short sentence."
    audio_variants = {
        "input_audio_wav_b64": [{"type": "text", "text": aq},
                                {"type": "input_audio", "input_audio": {"data": b64(m["wav"]), "format": "wav"}}],
        "audio_url_data_uri": [{"type": "text", "text": aq},
                               {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{b64(m['wav'])}"}}],
    }
    T["audio"] = {"ok": False, "variants": {}}
    for name, content in audio_variants.items():
        ok, out = chat(client, content); T["audio"]["variants"][name] = {"ok": ok, "detail": out[:300]}
        if ok: T["audio"]["ok"] = True; T["audio"]["working_variant"] = name; break

    if T["video"]["ok"] and T["audio"]["ok"]: mode = "native_av"
    elif T["image"]["ok"]: mode = "frames_plus_log"
    else: mode = "text_only_log"
    caps["PERCEPTION_MODE"] = mode
    OUT.write_text(json.dumps(caps, indent=2))
    print(f"\nPERCEPTION_MODE = {mode}\nwrote {OUT}")
    print("Reminder: copy anything surprising into FEEDBACK_NOTES.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
