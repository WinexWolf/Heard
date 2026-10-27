"""Run every demo session through the pipeline and cache the results (data/cache/<id>.json).

  uv run scripts/precompute_cache.py          # live Token Factory + Tavily if keys are set, else the labeled oracle stub
  uv run scripts/precompute_cache.py --stub   # force the non-model placeholder
"""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app.config import DATA, get_settings
from backend.app.pipeline import run


def main():
    live = get_settings().live_ready and "--stub" not in sys.argv
    print("mode:", "LIVE (Nebius Token Factory + Tavily)" if live else "ORACLE STUB (no model calls; labeled as such)")
    for sd in sorted((DATA / "sessions").iterdir()):
        if not (sd / "meta.json").exists(): continue
        sid = sd.name
        cdir = DATA / "cache" / sid; cdir.mkdir(parents=True, exist_ok=True)
        res = run.analyze(sid, live, emit=lambda e: print(f"  [{sid}] {e['stage']}") if e["stage"] in ("findings", "done") else None, out_dir=cdir)
        for f in res["findings"]:
            if f.get("after_audio"): f["after_audio"] = f"cache/{sid}/after_{f['finding']['id']}.wav"
        (DATA / "cache" / f"{sid}.json").write_text(json.dumps(res, indent=2))
        print(f"{sid}: {len(res['findings'])} findings, {sum(1 for f in res['findings'] if f['fixed'])} verified fixes [{res['source']}]")


if __name__ == "__main__":
    main()
