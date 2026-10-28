"""Benchmark: axe-core alone vs Heard on the 12 seeded bugs. Honest: reports categories where axe wins.

  uv run eval/run_eval.py            # uses data/cache/*.json (run scripts/precompute_cache.py first)
"""
import json, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright
from heard.app import a11y
from heard.app.config import DATA, ROOT

SITES = ["shop", "signup", "dashboard"]
REL_JS = """([targets, bugSel]) => {
  const bugs = [...document.querySelectorAll(bugSel)];
  return targets.some(t => { let el; try { el = document.querySelector(t) } catch(e) { return false }
    return el && bugs.some(b => b === el || b.contains(el) || el.contains(b)) })
}"""
REL_SEL_JS = """([sel, bugSel]) => { let el; try { el = document.querySelector(sel) } catch(e) { return false }
  const bugs = [...document.querySelectorAll(bugSel)]; return !!el && bugs.some(b => b === el || b.contains(el) || el.contains(b)) }"""


def axe_detects(page, bug) -> list[str]:
    page.add_script_tag(path=str(a11y.AXE_JS))
    viol = page.evaluate("axe.run().then(r => r.violations.map(v => ({id: v.id, targets: v.nodes.map(n => n.target.flat().join(' '))})))")
    hits = []
    for v in viol:
        if page.evaluate(REL_JS, [v["targets"], bug["selector"]]): hits.append(v["id"])
    return hits


def main():
    rows, source, models, cost = [], set(), {}, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "latency_s": 0.0, "cost_usd": 0.0}
    by_model, rejected_total, mode = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0}), 0, set()
    with sync_playwright() as pw:
        br = pw.chromium.launch(**a11y.chromium_launch_kwargs())
        for site in SITES:
            bugs = json.loads((ROOT / "data/bugs" / f"{site}.json").read_text())
            cache = DATA / "cache" / f"{site}_buggy.json"
            if not cache.exists(): sys.exit(f"missing {cache}: run scripts/precompute_cache.py first")
            res = json.loads(cache.read_text()); source.add(res["source"]); mode.add(res["perception_mode"])
            rejected_total += len(res["rejected_unsupported"])
            t = res["cost"]["total"]
            for k in ("calls", "input_tokens", "output_tokens", "latency_s", "cost_usd"): cost[k] += t[k]
            for m, v in res["cost"]["by_model"].items():
                by_model[m]["calls"] += v["calls"]; by_model[m]["cost_usd"] += v["cost_usd"]
            with a11y.serve_dir(ROOT / "demo_sites" / site / "buggy") as base:
                pg = br.new_page(); pg.goto(base + "index.html")
                for b in bugs:
                    axe_hits = axe_detects(pg, b)
                    heard = fixed = False; via = ""
                    for f in res["findings"]:
                        step = f.get("step") or {}
                        sel_ok = bool(step.get("selector")) and pg.evaluate(REL_SEL_JS, [step["selector"], b["selector"]])
                        if sel_ok or f["finding"]["issue_type"] == b["category"]:
                            heard = True; fixed = fixed or f["fixed"]; via = "selector" if sel_ok else "issue_type"
                    rows.append({"id": b["id"], "site": site, "category": b["category"], "description": b["description"],
                                 "axe_detected": bool(axe_hits), "axe_rules": axe_hits, "heard_detected": heard,
                                 "heard_matched_via": via, "fix_verified": heard and fixed})
        br.close()
    n = len(rows); axe_n = sum(r["axe_detected"] for r in rows); heard_n = sum(r["heard_detected"] for r in rows)
    fix_n = sum(r["fix_verified"] for r in rows)
    out = {"source": sorted(source), "perception_mode": sorted(mode), "total_bugs": n, "axe_detected": axe_n,
           "heard_detected": heard_n, "fixes_verified": fix_n, "rejected_unsupported": rejected_total,
           "cost": {**cost, "latency_s": round(cost["latency_s"], 2), "cost_usd": round(cost["cost_usd"], 6)},
           "by_model": dict(by_model), "bugs": rows,
           "matching_rule": "Heard detected = a supported finding whose step element is the bug element (or ancestor/descendant) OR whose issue_type equals the bug category on the same site. axe detected = a violation node that is the bug element (or ancestor/descendant)."}
    (ROOT / "eval/results.json").write_text(json.dumps(out, indent=2))
    placeholder = "oracle_stub" in source
    md = ["# Heard benchmark: axe-core vs Heard\n"]
    if placeholder:
        md.append("> **PLACEHOLDER — NOT A MEASUREMENT OF HEARD.** These Heard columns come from the non-model oracle stub (reference mapping), "
                  "so Heard detects what the stub is told to. The axe-core column IS real. Run `uv run scripts/precompute_cache.py` with live keys, then `uv run eval/run_eval.py`.\n")
    md.append(f"- Perception mode: {', '.join(sorted(mode))}  \n- Result source: {', '.join(sorted(source))}\n")
    md.append(f"| Metric | Value |\n|---|---|\n| axe-core detected | {axe_n}/{n} |\n| Heard detected | {heard_n}/{n} |\n| Fixes verified | {fix_n}/{heard_n} |\n| Rejected as unsupported | {rejected_total} |\n| Model calls / cost (USD, if prices set) / latency | {cost['calls']} / {cost['cost_usd']:.4f} / {cost['latency_s']:.1f}s |\n")
    md.append("## Per bug\n\n| Bug | Site | Category | axe | Heard | Fix verified |\n|---|---|---|---|---|---|")
    for r in rows: md.append(f"| {r['id']} | {r['site']} | {r['category']} | {'yes' if r['axe_detected'] else 'no'} | {'yes' if r['heard_detected'] else 'no'} | {'yes' if r['fix_verified'] else 'no'} |")
    cats = defaultdict(lambda: [0, 0, 0])
    for r in rows: c = cats[r["category"]]; c[0] += 1; c[1] += r["axe_detected"]; c[2] += r["heard_detected"]
    md.append("\n## Per category (bugs / axe / Heard)\n")
    for k, (t, a, h) in sorted(cats.items()): md.append(f"- {k}: {t} / {a} / {h}" + ("  ← axe >= Heard" if a >= h else ""))
    (ROOT / "eval/RESULTS.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
