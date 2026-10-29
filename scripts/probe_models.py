"""Milestone 0: capability probe.

Lists the perception provider's models and tests which inputs MODEL_PERCEPTION actually understands: text, image,
video and audio. Each test uses media with a distinctive answer (a red image saying HEARD, a video that turns blue then
green, a spoken "pineapple seventy three"), and only a correct answer counts: an HTTP 200 alone proves nothing.
Writes data/capabilities.json, including PERCEPTION_MODE and the audio variant perception should use.
"""
from __future__ import annotations
import base64, json, subprocess, sys, tempfile, time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from heard.app import a11y
from heard.app.config import get_settings

OUT = ROOT / "data" / "capabilities.json"
S = get_settings()
BASE, KEY = S.endpoint("perception")
MODEL = S.models["perception"]


def make_media(tmp: Path) -> dict[str, bytes]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = a11y.launch_chromium(pw); p = b.new_page(viewport={"width": 320, "height": 240})
        p.set_content("<body style='margin:0;background:#d00;display:grid;place-items:center;height:240px'>"
                      "<b style='color:#fff;font:60px sans-serif'>HEARD</b></body>")
        p.screenshot(path=str(tmp / "t.png")); b.close()
    run = lambda *a: subprocess.run(a, check=True, capture_output=True)
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2:r=5", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=2:r=5",
        "-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]", "-pix_fmt", "yuv420p", str(tmp / "t.mp4"))
    a11y.tts("The secret word is pineapple seventy three.", tmp / "t.wav")
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=5", "-i", str(tmp / "t.wav"),
        "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", str(tmp / "av.mp4"))
    return {k: (tmp / f).read_bytes() for k, f in (("png", "t.png"), ("mp4", "t.mp4"), ("wav", "t.wav"), ("av", "av.mp4"))}


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def chat(client: httpx.Client, content, extra: dict | None = None, max_tokens: int = 2048) -> tuple[bool, str]:
    """(answered, text). Reasoning models spend tokens thinking first, so max_tokens must leave room for the answer."""
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0, "messages": [{"role": "user", "content": content}], **(extra or {})}
    for attempt in range(6):
        try:
            r = client.post(f"{BASE}/chat/completions", json=body, timeout=180)
        except Exception as e:
            return False, f"exception: {e!r}"
        if r.status_code not in (429, 503): break
        time.sleep(min(30, 2 ** attempt))
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    return True, (r.json()["choices"][0]["message"].get("content") or "").strip()


def understood(answer: str, *words: str) -> bool:
    return all(w in answer.lower() for w in words)


def main() -> int:
    caps: dict = {"probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "provider": S.provider["perception"], "base_url": BASE,
                  "nemotron_models": [], "perception_model": MODEL, "tests": {}, "PERCEPTION_MODE": "text_only_log"}
    if not S.role_ready("perception"):
        caps["note"] = f"perception endpoint, key or MODEL_PERCEPTION not set (provider {S.provider['perception']}); defaulted to text_only_log."
        OUT.write_text(json.dumps(caps, indent=2)); print(caps["note"]); return 1

    client = httpx.Client(headers={"Authorization": f"Bearer {KEY}"})
    r = client.get(f"{BASE}/models", timeout=60)
    if r.status_code != 200:
        caps["note"] = f"model list failed: HTTP {r.status_code} {r.text[:300]}"
        OUT.write_text(json.dumps(caps, indent=2)); print(caps["note"]); return 1
    ids = [m["id"] for m in r.json().get("data", [])]
    caps["nemotron_models"] = sorted(i for i in ids if "nemotron" in i.lower())
    print("Nemotron models:"); [print("  ", i) for i in caps["nemotron_models"]]
    if MODEL not in ids:
        caps["note"] = f"MODEL_PERCEPTION={MODEL!r} is not in the model list. Pick an ID from nemotron_models, set it in .env, re-run."
        OUT.write_text(json.dumps(caps, indent=2)); print(caps["note"]); return 1

    with tempfile.TemporaryDirectory() as td:
        m = make_media(Path(td))
    T = caps["tests"]

    def test(name, content, words, extra=None):
        ok, out = chat(client, content, extra)
        res = {"ok": ok and understood(out, *words), "answered": ok, "detail": out[:300]}
        print(f"  {name}: {'understood' if res['ok'] else 'NOT understood'} -> {out[:90]!r}")
        return res

    print(f"\nProbing {MODEL} on {caps['provider']}:")
    T["text"] = test("text", "Reply with exactly one word: pong", ["pong"])
    T["image"] = test("image", [{"type": "text", "text": "What background colour and what word do you see? Answer as: colour, word"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64(m['png'])}"}}], ["red", "heard"])
    T["video"] = test("video", [{"type": "text", "text": "This video is a solid colour that changes once. Answer as: first colour, second colour"},
                                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64(m['mp4'])}"}}], ["blue", "green"])

    aq = "What exact sentence is spoken? If you hear no audio, say NO AUDIO."
    audio_variants = {   # first understood variant wins; a video's own soundtrack keeps sight and sound in one input
        "video_audio_track": ([{"type": "text", "text": aq}, {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64(m['av'])}"}}],
                              {"mm_processor_kwargs": {"use_audio_in_video": True}}),
        "audio_url_data_uri": ([{"type": "text", "text": aq}, {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{b64(m['wav'])}"}}], None),
        "input_audio_wav_b64": ([{"type": "text", "text": aq}, {"type": "input_audio", "input_audio": {"data": b64(m["wav"]), "format": "wav"}}], None),
    }
    T["audio"] = {"ok": False, "variants": {}}
    for name, (content, extra) in audio_variants.items():
        res = test(f"audio/{name}", content, ["pineapple"], extra)
        T["audio"]["variants"][name] = res
        if res["ok"]:
            T["audio"]["ok"] = True; T["audio"]["working_variant"] = name; break

    if T["video"]["ok"] and T["audio"]["ok"]: mode = "native_av"
    elif T["image"]["ok"]: mode = "frames_plus_log"
    else: mode = "text_only_log"
    caps["PERCEPTION_MODE"] = mode
    OUT.write_text(json.dumps(caps, indent=2))
    print(f"\nPERCEPTION_MODE = {mode}" + (f" (audio via {T['audio']['working_variant']})" if T["audio"]["ok"] else "") + f"\nwrote {OUT}")
    print("Reminder: copy anything surprising into FEEDBACK_NOTES.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
