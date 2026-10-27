# Submission assets

> Fill the `[LIVE: ...]` placeholders after running `scripts/precompute_cache.py` and `eval/run_eval.py` with real keys. Do not publish the placeholder numbers.

## Devpost description (draft)

### Inspiration
Accessibility linters read your code. But a blind user doesn't read your code; they *hear* your product. An icon button can pass every static check and still be announced as just "button". We wanted a tool that audits what the user actually hears.

### What it does
Heard takes a screen-reader session (screen video, announcement audio, timestamped speech log) and finds places where what the user **heard** does not match what is **on screen** or what the user **needs**. For each issue it searches the web (Tavily) for the relevant WCAG technique, patches the source with a minimal search/replace edit, and **verifies** the fix in a real browser against the accessibility tree and axe-core. You can press **Before** and **After** to hear the announcement change. A benchmark reports how many of 12 seeded bugs axe-core alone catches versus Heard: [LIVE: axe X/12 vs Heard Y/12, Z fixes verified].

### How we built it
- **Nebius Token Factory** (OpenAI-compatible API) runs three **NVIDIA Nemotron** models: **Nano Omni** for perception (video/audio/frames + speech log, strict JSON), **Super** for source patches, and **Ultra** as a one-shot escalation when a fix fails verification twice.
- **Tavily** is called at runtime for every finding, so the cited WCAG criterion and ARIA pattern come from live search, not model memory.
- A **deterministic evidence check** drops any finding whose quoted announcement is not in the speech log; the UI shows the rejected count.
- **Verification has no LLM**: Playwright + the Chromium accessibility tree + axe-core, with assertions per issue type (accessible name, role, label-in-name, live region, dialog focus, tab state, heading order) and a "no new axe violations" gate.
- Perception adapts to what the model supports (`native_av`, `frames_plus_log` or `text_only_log`), discovered by a capability probe rather than assumed. Mode used: [LIVE: PERCEPTION_MODE].
- FastAPI + SSE backend, React/Vite/Tailwind frontend that itself passes axe with zero violations (enforced by a test), per-model cost and latency tracking, per-IP rate limiting and cached demo results so judges need no login.

### Challenges
- Making the "heard vs. seen" comparison trustworthy: models invent quotes, so every claim is checked against the log.
- Honest evaluation: bugs like B03 (placeholder-only input) are *inaudible* because the browser derives a name from the placeholder; we kept them in the benchmark.
- Recording reproducible sessions without a human: a simulated screen reader built from the accessibility tree plus TTS, clearly labeled as simulated.

### Accomplishments we're proud of
Verification that rejects bad patches (every reference fix passes; every unpatched control fails), and a UI that is itself accessible.

### What we learned
See `FEEDBACK.md`.

### What's next
Real VoiceOver/NVDA recordings through the same pipeline, an upload flow, more bug classes and real-world sites, and a GitHub Action that fails a PR when a session regresses.

### Built with
Nebius Token Factory, NVIDIA Nemotron (Nano Omni, Super, Ultra), Tavily, Python, FastAPI, Playwright, axe-core, ffmpeg, React, TypeScript, Tailwind CSS.

## 3-minute demo video script

| Time | Shot | Voiceover / on screen |
|---|---|---|
| 0:00–0:25 | **Hook.** Screen: shop demo page, axe result shows the page "mostly fine". Play the real announcement audio of the cart button: "button". | "This page looks fine to a linter. This is what a blind user hears at the cart: 'button.' Linters read your code. Heard listens to your product." Show the Heard logo and tagline. |
| 0:25–1:45 | **Live run.** Heard UI, Session tab, pick the signup session, press **Run live**. Show stage pills advancing (Perception, Findings, Citation, Patch, Verify) and the live cost counter. Click the first finding: announced "Continue, button" vs visible "Create account". Open the Tavily citation link. Show the diff, the green "Verified" box, then press **Before** and **After**. Show the "rejected as unsupported" counter and explain it. | "Heard watched and listened to this session. Nemotron Omni flagged a button announced as 'Continue' that says 'Create account' on screen. Tavily found the WCAG label-in-name technique. Nemotron Super wrote a one-line fix. Verification loads the patched page in a browser and checks the accessibility tree and axe. Listen: before, after." |
| 1:45–2:25 | **Benchmark tab.** Table of 12 bugs, axe column vs Heard column; highlight the categories axe misses (repeated controls, vague links, un-announced errors) and one where axe wins or ties. | "We seeded 12 bugs. axe-core caught [LIVE: X]. Heard caught [LIVE: Y] and verified [LIVE: Z] fixes. We report honestly where axe does as well, and one bug nobody can hear." |
| 2:25–3:00 | **Architecture + usage.** Show the README mermaid diagram, then the Cost and models tab. | "Everything runs through Nebius Token Factory: Nemotron Omni perceives, Super patches, Ultra only steps in when a fix fails twice. Tavily grounds every citation at runtime. Verification is deterministic, no model. Open source, MIT. Heard: accessibility, by listening." |

Recording tips: use the cached result for the first take to check timing, then record the live run; keep the browser at 1400×900; turn on system audio capture so the Before/After clips are heard.
