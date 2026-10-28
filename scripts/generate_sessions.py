"""Generate reproducible *simulated screen reader* sessions for each buggy demo site.

Per site: record a video of keyboard/browse navigation, build the announcement for every step
as "{accessible name}, {role}" from the CDP accessibility tree, synthesize speech (macOS `say`
or espeak-ng), mux it into one audio track aligned to the step timestamps, and write
speech_log.json + steps.json next to session.mp4.
"""
from __future__ import annotations
import json, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright
from heard.app import a11y

ROOT = a11y.ROOT
SITES = ["shop", "signup", "dashboard"]
# Keyboard script per site, after the browse pass. T=Tab, E=Enter, S=Space.
SCRIPTS = {
    "shop": ["T"] * 16,
    "signup": list("TTTTSTE"),   # fill order, toggle the terms checkbox with Space, submit empty form
    "dashboard": list("TETTTET"),  # open settings modal, keep tabbing, activate the Orders tab
}
LIVE_JS = """() => [...document.querySelectorAll('[role=alert],[aria-live]')].map(e => e.innerText.trim()).join('|')"""
VISIBLE_JS = """() => document.body.innerText.split('\\n').map(l => l.trim()).filter(Boolean)"""
MODAL_JS = """() => { const m = document.querySelector('.modal'); return !!m && !m.hidden; }"""


def snippet(page, handle) -> str:
    return page.evaluate("(e)=>e.outerHTML.slice(0,240)", handle)


def selector(page, handle) -> str:
    return page.evaluate(f"({a11y.SELECTOR_JS})", handle)


def run_site(site: str, variant: str = "buggy") -> Path:
    src = ROOT / "demo_sites" / site / variant
    out = ROOT / "data" / "sessions" / f"{site}_{variant}"
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    steps: list[dict] = []
    with tempfile.TemporaryDirectory() as td, a11y.serve_dir(src) as base, sync_playwright() as pw:
        td = Path(td)
        browser = pw.chromium.launch(**a11y.chromium_launch_kwargs())
        ctx = browser.new_context(viewport={"width": 800, "height": 560})
        page = ctx.new_page(); t0 = time.time()
        (td / "frames").mkdir()
        frames: list[tuple[float, Path]] = []

        def wait(ms: int):
            """Wait while capturing screenshots at ~5 fps (video is assembled from them; no dependency
            on Playwright's bundled ffmpeg, so it behaves the same on macOS and in Docker)."""
            end = time.time() + ms / 1000
            while True:
                f = td / "frames" / f"{len(frames):05d}.png"
                page.screenshot(path=str(f)); frames.append((time.time() - t0, f))
                if time.time() >= end: break
                page.wait_for_timeout(int(min(150, max(0, (end - time.time()) * 1000))))

        page.goto(base); wait(700)
        clips: list[tuple[float, Path]] = []

        def record(kind, key, handle, extra=None):
            nonlocal clips
            t = time.time() - t0
            info = a11y.ax_info(page, handle) if handle else {"name": "", "role": "", "text": ""}
            text = extra.pop("announce_override") if extra and "announce_override" in extra else a11y.announcement(info)
            step = {"i": len(steps), "t": round(t, 2), "kind": kind, "key": key,
                    "selector": selector(page, handle) if handle else None,
                    "html": snippet(page, handle) if handle else "",
                    "name": info["name"], "role": info["role"], "visible_text": info.get("text", ""),
                    "announcement": text, **(extra or {})}
            steps.append(step)
            dwell = 1.0
            if text:
                wav = td / f"s{step['i']}.wav"; d = a11y.tts(text, wav); clips.append((t, wav)); dwell = max(1.0, d + 0.5)
            wait(int(dwell * 1000))

        # --- browse pass (virtual-cursor style): headings and images in DOM order
        for h in [e for e in page.query_selector_all("h1,h2,h3,img") if e.is_visible()]:
            h.scroll_into_view_if_needed()
            record("browse", "Down", h)

        # --- keyboard pass
        page.evaluate("document.activeElement && document.activeElement.blur(); window.scrollTo(0,0)")
        for k in SCRIPTS[site]:
            live_before, modal_before = page.evaluate(LIVE_JS), page.evaluate(MODAL_JS)
            vis_before = page.evaluate(VISIBLE_JS)
            key = {"T": "Tab", "E": "Enter", "S": "Space"}[k]
            page.keyboard.press(key if key != "Space" else " ")
            wait(250)
            active = page.evaluate_handle("document.activeElement")
            el = active.as_element()
            is_body = page.evaluate("(e)=>e===document.body", active)
            if k == "T":
                if is_body: break
                record("focus", key, el)
                continue
            # activation keys: report what a screen reader would actually say
            live_after, modal_after = page.evaluate(LIVE_JS), page.evaluate(MODAL_JS)
            vis_after = page.evaluate(VISIBLE_JS)
            change = []
            if modal_after and not modal_before: change.append("a modal dialog opened on screen")
            if vis_after != vis_before:
                new = [l for l in vis_after if l not in vis_before]
                gone = [l for l in vis_before if l not in vis_after]
                if new: change.append("screen now also shows: " + " / ".join(new)[:160])
                if gone: change.append("no longer shows: " + " / ".join(gone)[:100])
            ctrl = a11y.ax_info(page, el) if el else {"name": "", "role": ""}
            if live_after != live_before:
                spoken = live_after.split("|")[-1] if "|" in live_after else live_after
                record("action", key, el, {"announce_override": spoken, "screen_change": "; ".join(change), "live_region": True,
                                           "acted_on": a11y.announcement(ctrl)})
            else:
                post = a11y.announcement(ctrl) if k == "S" else ""   # Space on a custom checkbox: SR re-reads control
                record("action", key, el, {"announce_override": post, "screen_change": "; ".join(change), "live_region": False,
                                           "acted_on": a11y.announcement(ctrl),
                                           "silent": post == ""})
        wait(800)
        total = time.time() - t0
        ctx.close(); browser.close()
        lst = td / "frames.txt"
        with lst.open("w") as fh:
            for (ta, fa), nxt in zip(frames, frames[1:] + [(total, None)]):
                fh.write(f"file '{fa}'\nduration {max(0.04, nxt[0] - ta):.3f}\n")
            fh.write(f"file '{frames[-1][1]}'\n")
        video_path = td / "silent.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", "fps=10,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", str(video_path)], check=True)

        audio = out / "audio.wav"; a11y.mix_audio(clips, total + 0.5, audio)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path), "-i", str(audio),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "48k", "-shortest", str(out / "session.mp4")], check=True)
        # per-step "before" clips so the UI/verifier can compare later
        for s in steps:
            if s["announcement"]:
                a11y.tts(s["announcement"], out / f"step_{s['i']}_before.wav")

    (out / "steps.json").write_text(json.dumps(steps, indent=2))
    (out / "speech_log.json").write_text(json.dumps(
        [{"t": s["t"], "text": s["announcement"]} for s in steps if s["announcement"]], indent=2))
    (out / "meta.json").write_text(json.dumps({
        "id": f"{site}_{variant}", "site": site, "variant": variant, "label": "simulated screen reader",
        "source_dir": f"demo_sites/{site}/{variant}", "duration": round(total, 2), "steps": len(steps),
        "tts": "say" if shutil.which("say") else "espeak-ng"}, indent=2))
    print(f"{site}: {len(steps)} steps, {total:.1f}s -> {out}")
    return out


if __name__ == "__main__":
    for s in (sys.argv[1:] or SITES):
        run_site(s)
