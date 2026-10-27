# Feedback notes (raw, written as friction is hit)

Format: `- [date] [area] what happened -> what I did`

- [2026-10-26] [env] Build sandbox is a Linux VM (Python 3.10, no espeak-ng preinstalled), not the Mac; no Nebius/Tavily keys available at build time. All live-API code paths are written against the OpenAI-compatible schema and must be exercised once keys are set (`python scripts/probe_models.py`).
- [2026-10-26] [method] Seeded bug B03 (input with placeholder, no label): Chromium computes the accessible name from the placeholder, so a screen reader announces "Email address, edit text". The speech log therefore contains no audible symptom; a listening-based auditor cannot see this one. Kept in the benchmark on purpose (honest eval); verifier requires a real label.
- [2026-10-26] [env] Playwright 1.64's bundled video recorder needs its own ffmpeg build that was not available offline; session generator captures screenshots and assembles video with system ffmpeg instead (portable).
- [2026-10-26] [docs] Token Factory quickstart (docs.tokenfactory.nebius.com/quickstart) shows only a text content part and a DeepSeek model ID. It says nothing about Nemotron models or image/video/audio content parts, so the multimodal request shape for the Omni model had to be probed empirically (scripts/probe_models.py records every variant tried).
- [2026-10-26] [docs] `nebius ai endpoint create` has no standalone CLI reference page; the flags (--env, --env-secret, --auth none|token, --registry-*) live on the `nebius ai create` page under `--type endpoint`. The serverless quickstart example uses `--auth token` while the CLI default is `none`; easy to deploy an auth-protected demo by accident when judges need a no-login URL.
- [2026-10-26] [docs] Serverless quickstart does not say how to pass env vars or registry credentials (only found on the CLI reference page).
