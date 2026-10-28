from __future__ import annotations
import asyncio, json, logging, queue, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import DATA, ROOT, get_settings
from .ratelimit import RateLimiter
from .pipeline import run

log = logging.getLogger("heard")
app = FastAPI(title="Heard", version="1.0")
limiter = RateLimiter(get_settings().rate_limit)
MEDIA_DIRS = ("sessions", "runs", "cache")


def sse(ev: dict) -> str:
    return f"data: {json.dumps(ev)}\n\n"


def session_ids() -> list[str]:
    return sorted(p.name for p in (DATA / "sessions").iterdir() if (p / "meta.json").exists())


@app.get("/api/capabilities")
def capabilities():
    s = get_settings(); c = s.capabilities()
    return {"perception_mode": c.get("PERCEPTION_MODE"), "models": c["models"], "live_ready": c["live_ready"],
            "demo_cache": s.demo_cache, "rate_limit_per_hour": s.rate_limit,
            "probe_note": c.get("note")}


@app.get("/api/sessions")
def sessions():
    out = []
    for sid in session_ids():
        meta = json.loads((DATA / "sessions" / sid / "meta.json").read_text())
        out.append({**meta, "has_cache": (DATA / "cache" / f"{sid}.json").exists(),
                    "video": f"/media/sessions/{sid}/session.mp4"})
    return out


def load_result(sid: str) -> dict | None:
    for p in (DATA / "cache" / f"{sid}.json", DATA / "runs" / sid / "result.json"):
        if p.exists(): return json.loads(p.read_text())
    return None


@app.get("/api/sessions/{sid}/result")
def result(sid: str):
    if sid not in session_ids(): raise HTTPException(404, "unknown session")
    r = load_result(sid)
    if r is None: raise HTTPException(404, "no cached or previous result for this session")
    return r


@app.get("/api/sessions/{sid}/steps")
def steps(sid: str):
    if sid not in session_ids(): raise HTTPException(404, "unknown session")
    return json.loads((DATA / "sessions" / sid / "steps.json").read_text())


@app.post("/api/sessions/{sid}/analyze")
async def analyze(sid: str, request: Request, live: bool = False):
    if sid not in session_ids(): raise HTTPException(404, "unknown session")
    s = get_settings()
    if not live:
        cached = (DATA / "cache" / f"{sid}.json")
        if not cached.exists(): raise HTTPException(404, "no cached result; use live=true")
        res = json.loads(cached.read_text())

        async def replay():
            yield sse({"stage": "perception", "status": "cached", "mode": res["perception_mode"], "source": res["source"]})
            yield sse({"stage": "findings", "supported": [f["finding"] for f in res["findings"]],
                       "rejected": res["rejected_unsupported"], "cost": res["cost"]["total"], "cached": True})
            for f in res["findings"]:
                fid = f["finding"]["id"]
                yield sse({"stage": "citation", "finding": fid, "citations": f["citations"], "query": f.get("query")})
                yield sse({"stage": "patch", "finding": fid, "edits": f["final"]["edits"] if f.get("final") else [], "rationale": (f.get("final") or {}).get("rationale", "")})
                yield sse({"stage": "verify", "finding": fid, "passed": f["fixed"], "reason": (f.get("final") or {}).get("reason", "")})
                await asyncio.sleep(0.05)
            yield sse({"stage": "done", "result": res, "cached": True})
        return StreamingResponse(replay(), media_type="text/event-stream")

    ip = request.client.host if request.client else "unknown"
    ok, retry = limiter.check(ip)
    if not ok:
        return JSONResponse({"error": f"Rate limit: {s.rate_limit} live analyses per hour. Try again in {retry}s, or view the cached result."},
                            status_code=429, headers={"Retry-After": str(retry)})
    if not s.live_ready:
        raise HTTPException(503, "Live mode is not configured on this server (set the Token Factory and Tavily keys). Showing cached results only.")
    q: queue.Queue = queue.Queue()

    def work():
        try:
            run.analyze_live(sid, emit=q.put)
        except Exception as e:  # never leak secrets: only the message type + text we raised
            log.exception("analysis failed")
            q.put({"stage": "error", "message": str(e)[:300]})
        q.put(None)
    threading.Thread(target=work, daemon=True).start()

    async def stream():
        while True:
            try: ev = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                if await request.is_disconnected(): return
                continue
            if ev is None: return
            yield sse(ev)
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/benchmark")
def benchmark():
    p = ROOT / "eval" / "results.json"
    if not p.exists(): raise HTTPException(404, "no benchmark yet: run eval/run_eval.py")
    return json.loads(p.read_text())


@app.get("/media/{path:path}")
def media(path: str):
    top = path.split("/")[0]
    f = (DATA / path).resolve()
    if top not in MEDIA_DIRS or not str(f).startswith(str(DATA.resolve())) or not f.is_file() or f.suffix not in (".mp4", ".wav"):
        raise HTTPException(404)
    return FileResponse(f)


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
