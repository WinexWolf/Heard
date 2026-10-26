"""Regenerate demo_sites/<site>/fixed from buggy/ by applying reference edits.

The fixed copies are the human-written reference solutions (used for the "fixed"
demo pages and for sanity-checking the verifier). They are NEVER shown to the models.
"""
import shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "demo_sites"

EDITS = {
 "shop": {
  "index.html": [
   ('<button id="cart-btn" class="icon-btn" type="button">', '<button id="cart-btn" class="icon-btn" type="button" aria-label="Open cart, 5 items">'),
   ('<img class="hero" src="hero.svg" width="640" height="160">', '<img class="hero" src="hero.svg" width="640" height="160" alt="Spring sale banner: pixel keyboards">'),
   ('<a class="learn-more" href="#pixel-60">Learn more</a>', '<a class="learn-more" href="#pixel-60">Learn more<span class="sr-only"> about Pixel 60</span></a>'),
   ('<a class="learn-more" href="#pixel-75">Learn more</a>', '<a class="learn-more" href="#pixel-75">Learn more<span class="sr-only"> about Pixel 75</span></a>'),
   ('<a class="learn-more" href="#pixel-tkl">Learn more</a>', '<a class="learn-more" href="#pixel-tkl">Learn more<span class="sr-only"> about Pixel TKL</span></a>'),
   ('<span>Pixel 60 x 1</span><button type="button" class="edit-btn">', '<span>Pixel 60 x 1</span><button type="button" class="edit-btn" aria-label="Edit Pixel 60">'),
   ('<span>Pixel 75 x 2</span><button type="button" class="edit-btn">', '<span>Pixel 75 x 2</span><button type="button" class="edit-btn" aria-label="Edit Pixel 75">'),
   ('<span>Keycap set x 1</span><button type="button" class="edit-btn">', '<span>Keycap set x 1</span><button type="button" class="edit-btn" aria-label="Edit Keycap set">'),
   ('<span>USB-C cable x 3</span><button type="button" class="edit-btn">', '<span>USB-C cable x 3</span><button type="button" class="edit-btn" aria-label="Edit USB-C cable">'),
   ('<span>Switch pack x 1</span><button type="button" class="edit-btn">', '<span>Switch pack x 1</span><button type="button" class="edit-btn" aria-label="Edit Switch pack">'),
  ],
 },
 "signup": {
  "index.html": [
   ('<input id="email" type="email" placeholder="Email address" autocomplete="email">', '<label for="email">Email address</label>\n<input id="email" type="email" placeholder="you@example.com" autocomplete="email">'),
   ('<div id="email-error" class="error"></div>', '<div id="email-error" class="error" role="alert"></div>'),
   ('<div id="terms" class="checkbox" tabindex="0">', '<div id="terms" class="checkbox" tabindex="0" role="checkbox" aria-checked="false" aria-labelledby="terms-label">'),
   ('<span>I agree to the terms</span>', '<span id="terms-label">I agree to the terms</span>'),
   ('aria-label="Continue">Create account', '>Create account'),
  ],
  "app.js": [
   ("const toggle = () => terms.classList.toggle('on');", "const toggle = () => { terms.classList.toggle('on'); terms.setAttribute('aria-checked', terms.classList.contains('on') ? 'true' : 'false'); };"),
  ],
 },
 "dashboard": {
  "index.html": [
   ('<div class="btn" id="export" tabindex="0">Export CSV</div>', '<button type="button" id="export">Export CSV</button>'),
   ('<h3 id="overview-heading">', '<h2 id="overview-heading">'),
   ('Overview</h3>', 'Overview</h2>'),
   ('<div class="tabs">', '<div class="tabs" role="tablist" aria-label="Dashboard sections">'),
   ('<div class="tab active" tabindex="0" data-panel="panel-overview">', '<div class="tab active" role="tab" id="tab-overview" aria-selected="true" aria-controls="panel-overview" tabindex="0" data-panel="panel-overview">'),
   ('<div class="tab" tabindex="0" data-panel="panel-orders">', '<div class="tab" role="tab" id="tab-orders" aria-selected="false" aria-controls="panel-orders" tabindex="0" data-panel="panel-orders">'),
   ('<div class="tab" tabindex="0" data-panel="panel-users">', '<div class="tab" role="tab" id="tab-users" aria-selected="false" aria-controls="panel-users" tabindex="0" data-panel="panel-users">'),
   ('<div class="panel" id="panel-overview">', '<div class="panel" id="panel-overview" role="tabpanel" aria-labelledby="tab-overview">'),
   ('<div class="panel" id="panel-orders" hidden>', '<div class="panel" id="panel-orders" role="tabpanel" aria-labelledby="tab-orders" hidden>'),
   ('<div class="panel" id="panel-users" hidden>', '<div class="panel" id="panel-users" role="tabpanel" aria-labelledby="tab-users" hidden>'),
   ('<div id="modal" class="modal" hidden><div class="modal-box">', '<div id="modal" class="modal" hidden><div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="modal-title">'),
  ],
  "app.js": [
   ("tabs.forEach(x => x.classList.remove('active'));", "tabs.forEach(x => { x.classList.remove('active'); x.setAttribute('aria-selected', 'false'); });"),
   ("t.classList.add('active');", "t.classList.add('active'); t.setAttribute('aria-selected', 'true');"),
   ("document.getElementById('open-modal').addEventListener('click', () => { modal.hidden = false; });",
    "const opener = document.getElementById('open-modal');\nopener.addEventListener('click', () => { modal.hidden = false; document.getElementById('close-modal').focus(); });\nmodal.addEventListener('keydown', e => { if (e.key === 'Escape') { modal.hidden = true; opener.focus(); } });"),
   ("document.getElementById('close-modal').addEventListener('click', () => { modal.hidden = true; });",
    "document.getElementById('close-modal').addEventListener('click', () => { modal.hidden = true; opener.focus(); });"),
  ],
 },
}

def main():
    for site, files in EDITS.items():
        src, dst = ROOT / site / "buggy", ROOT / site / "fixed"
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(src, dst)
        for fname, edits in files.items():
            p = dst / fname; text = p.read_text()
            for old, new in edits:
                if text.count(old) != 1:
                    sys.exit(f"{site}/{fname}: expected exactly one match for: {old[:60]!r} (found {text.count(old)})")
                text = text.replace(old, new)
            p.write_text(text)
    print("fixed/ copies regenerated")

if __name__ == "__main__":
    main()
