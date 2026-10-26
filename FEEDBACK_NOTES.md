# Feedback notes (raw, written as friction is hit)

Format: `- [date] [area] what happened -> what I did`

- [2026-10-26] [env] Build sandbox is a Linux VM (Python 3.10, no espeak-ng preinstalled), not the Mac; no Nebius/Tavily keys available at build time. All live-API code paths are written against the OpenAI-compatible schema and must be exercised once keys are set (`python scripts/probe_models.py`).
