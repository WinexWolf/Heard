# Feedback: Nebius Token Factory and NVIDIA Nemotron

Built from `FEEDBACK_NOTES.md`, which was written while building Heard. **Status:** the build environment had no Token Factory key, so everything below
about live API behaviour is marked *to confirm on first live run*. Observations about docs and onboarding were made against the current public docs.

## What we tried to use
- Token Factory OpenAI-compatible `/chat/completions` for three roles: perception (Nemotron Omni), patching (Nemotron Super), escalation (Nemotron Ultra).
- Multimodal input (video + audio + images) to the perception model, discovered at runtime by `scripts/probe_models.py`.

## Docs and onboarding (verified)
1. **Quickstart is text-only.** It shows a single `text` content part and a non-Nemotron model ID; it does not mention Nemotron, or the `image_url` / `video_url` / `input_audio` content-part shapes. For an app whose headline feature is audio+video input, the request format had to be probed instead of read. *Suggestion:* a per-model "supported input modalities and exact content-part JSON" table next to the model list.
2. **Serverless deployment docs are split.** The endpoint flags (`--env`, `--env-secret`, `--auth none|token`, `--registry-*`) are on the `nebius ai create` reference page, not on a page for `nebius ai endpoint create`. The quickstart example uses `--auth token`, while the CLI default is `none`, which is easy to trip over when the goal is a no-login public demo. The quickstart does not mention env vars or registry credentials.
3. **Base URL** (`https://api.tokenfactory.nebius.com/v1/`) is clearly documented, which made `.env.example` straightforward.

## Token Factory API behaviour (to confirm on first live run)
- Does the model list endpoint expose modality capabilities, or only IDs?
- Max request size for a base64 `video_url` data URI; is there an upload route for larger video?
- Whether `usage` (prompt/completion tokens) is returned for multimodal calls, and how video/audio tokens are counted (Heard's cost tracker depends on it).
- Rate limits and latency for the Omni model on a ~25 s video.

## NVIDIA Nemotron models (to confirm on first live run)
- Quality of strict-JSON output from Omni vs Super vs Ultra (Heard validates against a pydantic schema and retries once).
- Whether Omni's audio understanding picks out *which words were spoken* well enough for the "quote announced_text exactly" rule, or whether the speech-log text path is doing the work. The deterministic evidence check exists because this is the thing most worth measuring.

## What worked well
- OpenAI-compatible surface meant no custom client: plain `httpx` against `/chat/completions` was enough.
