"""Drive a running web app the way a screen-reader user would and record what is announced.

No model, audio or video: this is the cheap, deterministic half of Heard that runs on every push. Each page gets a
browse pass (headings and images) and a Tab pass through every focusable element. Heard never clicks on its own;
Enter/Space/typing only happen inside flows the project declares, so a scan cannot press "Delete account".
"""
from __future__ import annotations
import time
from playwright.sync_api import Browser, Page, sync_playwright
from . import a11y

KEYS = {"tab": "Tab", "shift+tab": "Shift+Tab", "enter": "Enter", "space": " ", "escape": "Escape"}
LIVE_JS = """() => [...document.querySelectorAll('[role=alert],[role=status],[aria-live]')].map(e => e.innerText.trim()).join('|')"""
VISIBLE_JS = """() => document.body.innerText.split('\\n').map(l => l.trim()).filter(Boolean)"""
DIALOG_JS = """() => [...document.querySelectorAll('dialog[open],[role=dialog],[role=alertdialog],.modal')].some(e => e.offsetParent !== null)"""


class Recorder:
    def __init__(self, page: Page):
        self.page, self.steps = page, []

    def record(self, kind: str, key: str, handle, extra: dict | None = None) -> dict:
        p = self.page
        info = a11y.ax_info(p, handle) if handle else {"name": "", "role": "", "text": ""}
        extra = dict(extra or {})
        text = extra.pop("announce_override") if "announce_override" in extra else a11y.announcement(info)
        i = len(self.steps)
        step = {"i": i, "t": float(i), "kind": kind, "key": key,
                "selector": p.evaluate(f"({a11y.SELECTOR_JS})", handle) if handle else None,
                "html": p.evaluate("(e)=>e.outerHTML.slice(0,240)", handle) if handle else "",
                "name": info["name"], "role": info["role"], "visible_text": info.get("text", ""),
                "announcement": text, **extra}
        self.steps.append(step)
        return step

    def focused(self):
        el = self.page.evaluate_handle("document.activeElement").as_element()
        return None if el is None or self.page.evaluate("(e)=>e===document.body", el) else el

    def browse(self):
        for h in [e for e in self.page.query_selector_all("h1,h2,h3,h4,h5,h6,img") if e.is_visible()]:
            self.record("browse", "Down", h)

    def tab_through(self, max_tabs: int = 200):
        first = None
        for _ in range(max_tabs):
            self.page.keyboard.press("Tab"); self.page.wait_for_timeout(30)
            el = self.focused()
            if el is None: break
            sel = self.page.evaluate(f"({a11y.SELECTOR_JS})", el)
            if sel == first: break                      # focus wrapped around
            first = first or sel
            self.record("focus", "Tab", el)

    def act(self, key: str):
        """Press an activation key and record what a screen reader would actually say about it."""
        p = self.page
        live0, dlg0, vis0 = p.evaluate(LIVE_JS), p.evaluate(DIALOG_JS), p.evaluate(VISIBLE_JS)
        p.keyboard.press(KEYS[key]); p.wait_for_timeout(250)
        live1, dlg1, vis1 = p.evaluate(LIVE_JS), p.evaluate(DIALOG_JS), p.evaluate(VISIBLE_JS)
        change = []
        if dlg1 and not dlg0: change.append("a modal dialog opened on screen")
        if vis1 != vis0:
            new = [l for l in vis1 if l not in vis0]; gone = [l for l in vis0 if l not in vis1]
            if new: change.append("screen now also shows: " + " / ".join(new)[:160])
            if gone: change.append("no longer shows: " + " / ".join(gone)[:100])
        el = self.focused()
        ctrl = a11y.announcement(a11y.ax_info(p, el)) if el else ""
        if live1 != live0:
            spoken = live1.split("|")[-1]
            self.record("action", key, el, {"announce_override": spoken, "screen_change": "; ".join(change), "live_region": True, "acted_on": ctrl})
        else:
            post = ctrl if key == "space" else ""       # Space on a toggle: the screen reader re-reads the control
            self.record("action", key, el, {"announce_override": post, "screen_change": "; ".join(change), "live_region": False,
                                            "acted_on": ctrl, "silent": post == ""})


def scan_page(page: Page, url: str) -> list[dict]:
    r = Recorder(page)
    page.goto(url, wait_until="networkidle"); r.browse()
    page.goto(url, wait_until="networkidle"); r.tab_through()
    return r.steps


def run_flow(page: Page, url: str, steps: list) -> list[dict]:
    """Scripted keyboard flow: "tab" / "shift+tab" record focus, "enter" / "space" / "escape" act, {"type": "..."} types."""
    r = Recorder(page)
    page.goto(url, wait_until="networkidle")
    for s in steps:
        if isinstance(s, dict) and "type" in s:
            page.keyboard.type(str(s["type"]))
        elif s in ("tab", "shift+tab"):
            page.keyboard.press(KEYS[s]); page.wait_for_timeout(30)
            el = r.focused()
            if el: r.record("focus", KEYS[s], el)
        elif s in KEYS:
            r.act(s)
        else:
            raise ValueError(f"unknown flow step {s!r} (use tab, shift+tab, enter, space, escape or {{type = \"...\"}})")
    return r.steps


def snapshot(base_url: str, pages: list[str], flows: dict[str, dict] | None = None, browser: Browser | None = None) -> dict:
    """Speech snapshot of a running app: {"pages": {"/path": steps, "flow:name": steps}}. Reuses `browser` if given."""
    if browser is None:
        with sync_playwright() as pw:
            br = a11y.launch_chromium(pw)
            try:
                return snapshot(base_url, pages, flows, br)
            finally:
                br.close()
    base = base_url.rstrip("/")
    out: dict[str, list[dict]] = {}
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    try:
        page = ctx.new_page()
        for path in pages:
            out[path] = scan_page(page, base + path)
        for name, f in (flows or {}).items():
            out[f"flow:{name}"] = run_flow(page, base + f.get("page", "/"), f.get("steps", []))
    finally:
        ctx.close()
    return {"version": 1, "url": base, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pages": out}
