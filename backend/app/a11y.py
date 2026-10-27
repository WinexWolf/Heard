"""Browser helpers shared by the session generator, verifier and eval: launching Chromium,
serving a site directory, and reading accessible name/role from the CDP accessibility tree."""
from __future__ import annotations
import functools, glob, re, http.server, os, shutil, socketserver, subprocess, threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AXE_JS = ROOT / "scripts" / "node_modules" / "axe-core" / "axe.min.js"

ROLE_WORDS = {"img": "graphic", "image": "graphic", "textbox": "edit text", "checkbox": "check box", "combobox": "combo box",
              "generic": "clickable", "StaticText": "text", "link": "link", "button": "button",
              "tab": "tab", "dialog": "dialog", "alert": "alert", "tablist": "tab list"}

SELECTOR_JS = """(el) => {
  if (el.id) return '#' + CSS.escape(el.id);
  const parts = [];
  while (el && el.nodeType === 1 && el !== document.body) {
    let s = el.tagName.toLowerCase();
    const cls = [...el.classList][0]; if (cls) s += '.' + CSS.escape(cls);
    const sib = [...el.parentNode.children].filter(c => c.tagName === el.tagName);
    if (sib.length > 1) s += ':nth-of-type(' + (sib.indexOf(el) + 1) + ')';
    parts.unshift(s); el = el.parentNode;
  }
  return parts.join(' > ');
}"""


def chromium_launch_kwargs() -> dict:
    kw: dict = {"args": ["--disable-background-networking"] + (["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else [])}
    exe = os.getenv("CHROMIUM_PATH")
    if not exe:
        found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
        exe = found[-1] if found else None
    if exe:
        kw["executable_path"] = exe
    return kw


@contextmanager
def serve_dir(directory: Path):
    """Serve a static directory on a free localhost port; yields the base URL."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a, **k: None  # type: ignore
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k): pass
    h = functools.partial(Quiet, directory=str(directory))
    srv = socketserver.TCPServer(("127.0.0.1", 0), h)
    srv.allow_reuse_address = True
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/"
    finally:
        srv.shutdown(); srv.server_close()


def ax_info(page, handle) -> dict:
    """Return {name, role, level, checked, selected, text}. Uses a fresh CDP session per call."""
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("DOM.enable"); cdp.send("Accessibility.enable")
        doc = cdp.send("DOM.getDocument", {"depth": 0})
        tag = "data-heard-probe"
        page.evaluate("(e)=>e.setAttribute('data-heard-probe','1')", handle)
        try:
            q = cdp.send("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": f"[{tag}]"})
            tree = cdp.send("Accessibility.getPartialAXTree", {"nodeId": q["nodeId"], "fetchRelatives": False})
        finally:
            page.evaluate("(e)=>e.removeAttribute('data-heard-probe')", handle)
        n = tree["nodes"][0] if tree.get("nodes") else {}
        props = {p["name"]: p["value"].get("value") for p in n.get("properties", [])}
        return {"name": (n.get("name", {}).get("value") or "").strip(),
                "role": n.get("role", {}).get("value", ""),
                "level": props.get("level"), "checked": props.get("checked"),
                "selected": props.get("selected"), "expanded": props.get("expanded"),
                "text": (page.evaluate("(e)=>(e.innerText||'').trim()", handle) or "")[:120]}
    finally:
        cdp.detach()


def announcement(info: dict) -> str:
    """Simulated screen-reader utterance: '{name}, {role}' (empty name -> just role)."""
    role = info["role"]
    name = info["name"]
    if role in ("generic", "StaticText", "none") and not name:
        name = info.get("text", "")
    word = ROLE_WORDS.get(role, role)
    if role == "heading" and info.get("level"):
        word = f"heading level {info['level']}"
    if role == "checkbox" and info.get("checked") is not None:
        word += ", checked" if str(info["checked"]).lower() == "true" else ", not checked"
    if role == "tab" and info.get("selected") is True:
        word += ", selected"
    name = re.sub(r"[^\w\s,.'$#%&/:-]", "", name).strip()   # drop decorative glyphs (e.g. CSS check marks)
    return f"{name}, {word}" if name else word


def tts(text: str, out_wav: Path) -> float:
    """Synthesize speech to a 16kHz mono wav. macOS `say` if present, else espeak-ng. Returns seconds."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("say"):
        aiff = out_wav.with_suffix(".aiff")
        subprocess.run(["say", "-o", str(aiff), text], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(out_wav)], check=True)
        aiff.unlink(missing_ok=True)
    elif shutil.which("espeak-ng"):
        subprocess.run(["espeak-ng", "-s", "165", "-w", str(out_wav), text], check=True)
        tmp = out_wav.with_suffix(".tmp.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out_wav), "-ar", "16000", "-ac", "1", str(tmp)], check=True)
        tmp.replace(out_wav)
    else:
        raise RuntimeError("No TTS available: install espeak-ng or run on macOS (say)")
    return duration(out_wav)


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip() or 0)


def mix_audio(clips: list[tuple[float, Path]], total: float, out_wav: Path) -> None:
    """Place each clip at t seconds (ffmpeg adelay + amix) into one track of length `total`."""
    if not clips:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono", "-t", str(total), str(out_wav)], check=True)
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", str(total), "-i", "anullsrc=r=16000:cl=mono"]
    for _, p in clips: cmd += ["-i", str(p)]
    fl = "".join(f"[{i+1}:a]adelay={int(t*1000)}|{int(t*1000)}[a{i}];" for i, (t, _) in enumerate(clips))
    fl += "[0:a]" + "".join(f"[a{i}]" for i in range(len(clips))) + f"amix=inputs={len(clips)+1}:normalize=0:duration=first[out]"
    cmd += ["-filter_complex", fl, "-map", "[out]", "-ar", "16000", "-ac", "1", str(out_wav)]
    subprocess.run(cmd, check=True)
