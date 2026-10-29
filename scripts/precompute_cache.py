"""Run every demo session through the pipeline and cache the results (data/cache/<id>.json).

  uv run scripts/precompute_cache.py          # live models + Tavily if keys are set, else the labeled oracle stub
  uv run scripts/precompute_cache.py --stub   # force the non-model placeholder
  uv run scripts/precompute_cache.py shop_buggy   # only these sessions
"""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from heard.app.config import DATA, get_settings
from heard.app.pipeline import run


def main():
    live = get_settings().live_ready and "--stub" not in sys.argv
    print("mode:", "LIVE (Nemotron on NVIDIA + Nebius Token Factory, Tavily)" if live else "ORACLE STUB (no model calls; labeled as such)")
    only = [a for a in sys.argv[1:] if not a.startswith("--")]     # optional session ids, e.g. shop_buggy
    failed = []
    for sd in sorted((DATA / "sessions").iterdir()):
        if not (sd / "meta.json").exists(): continue
        sid = sd.name
        if only and sid not in only: continue
        cdir = DATA / "cache" / sid; cdir.mkdir(parents=True, exist_ok=True)
        try:
            res = run.analyze(sid, live, emit=lambda e: print(f"  [{sid}] {e['stage']}") if e["stage"] in ("findings", "done") else None, out_dir=cdir)
        except Exception as e:              # one session failing (e.g. a busy endpoint) must not lose the others
            print(f"{sid}: FAILED, previous cache kept ({type(e).__name__}: {str(e)[:160]})"); failed.append(sid); continue
        for f in res["findings"]:
            if f.get("after_audio"): f["after_audio"] = f"cache/{sid}/after_{f['finding']['id']}.wav"
        (DATA / "cache" / f"{sid}.json").write_text(json.dumps(res, indent=2))
        print(f"{sid}: {len(res['findings'])} findings, {sum(1 for f in res['findings'] if f['fixed'])} verified fixes [{res['source']}]")
    if failed:
        print(f"failed: {', '.join(failed)}; re-run with: uv run scripts/precompute_cache.py {' '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
