# heard

Catch accessibility regressions on every push by listening to your app the way a screen-reader user does.

```bash
npx heard init       # writes heard.toml: your app's URL, pages and optional flows
npx heard snapshot   # records what a screen-reader user hears -> heard.snapshot.json (commit it)
npx heard check      # re-records, diffs, audits only what changed; exit 1 on regressions
npx heard report     # opens the last check as a page
npx heard fix        # patches your source; keeps only fixes verified on the running app
```

This package is a thin launcher for the Python CLI of the same version, run through [uv](https://docs.astral.sh/uv/) (`uvx heard==<version>`), so you need uv installed. On first run Heard downloads Playwright's Chromium.

`check` and `fix` call NVIDIA Nemotron models on Nebius Token Factory. Set `NEBIUS_API_KEY`, `NEBIUS_BASE_URL` and `MODEL_PERCEPTION` (plus `MODEL_PATCH`, and optionally `MODEL_ESCALATION`, for `fix`). Without keys, `check` still reports exactly what users will hear differently.

Docs, GitHub Action example and source: https://github.com/WinexWolf/Heard
