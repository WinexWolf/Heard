"""Stage 3: Tavily web search to ground the WCAG citation and the ARIA pattern.

The criterion comes from the issue type, not the model's guess, and search is limited to w3.org, so every
citation is a W3C Understanding, Technique or ARIA Authoring Practices page. Non-empty results are cached per
query for TTL (30 days), in memory and optionally on disk.
"""
from __future__ import annotations
import json, re, time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from ..schemas import Citation

# Canonical criterion per issue type: the citation and the patch grounding follow the issue, not a guess.
CRITERION = {"missing_name": "4.1.2", "missing_alt": "1.1.1", "missing_label": "1.3.1", "vague_link": "2.4.4",
             "repeated_control": "2.4.6", "error_not_announced": "4.1.3", "label_in_name": "2.5.3",
             "missing_state": "4.1.2", "div_button": "4.1.2", "modal_dialog": "4.1.2", "tab_widget": "4.1.2", "heading_skip": "1.3.1"}
WCAG_NAMES = {"4.1.2": "Name, Role, Value", "1.1.1": "Non-text Content", "1.3.1": "Info and Relationships",
              "2.4.4": "Link Purpose (In Context)", "2.5.3": "Label in Name", "4.1.3": "Status Messages",
              "2.4.6": "Headings and Labels", "3.3.1": "Error Identification", "2.1.1": "Keyboard"}
TECHNIQUE = {"missing_name": "icon button aria-label accessible name", "missing_alt": "img alt text",
             "missing_label": "form input label", "vague_link": "link text purpose context",
             "repeated_control": "aria-label distinguish repeated buttons", "error_not_announced": "role=alert live region error message",
             "label_in_name": "label in name aria-label visible text", "missing_state": "custom checkbox role=checkbox aria-checked",
             "div_button": "use native button element instead of div role=button", "modal_dialog": "dialog role aria-modal focus management",
             "tab_widget": "tabs pattern role=tablist tab tabpanel aria-selected", "heading_skip": "heading levels do not skip"}
DOMAINS = ["w3.org"]
TTL = 30 * 24 * 3600
_cache: dict[str, dict] = {}            # query -> {"at": epoch seconds, "results": [...]}


def criterion(issue_type: str, guess: str = "") -> str:
    """Known issue types map to a fixed criterion; only `other` falls back to a well-formed model guess."""
    if issue_type in CRITERION:
        return CRITERION[issue_type]
    return guess if re.fullmatch(r"\d\.\d\.\d{1,2}", guess or "") else "4.1.2"


def build_query(issue_type: str, wcag: str) -> str:
    c = criterion(issue_type, wcag)
    return f"WCAG 2.2 {c} {WCAG_NAMES.get(c, '')} {TECHNIQUE.get(issue_type, issue_type)} technique".replace("  ", " ").strip()


def _w3c(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in DOMAINS)


def _fresh(entry) -> bool:
    return isinstance(entry, dict) and bool(entry.get("results")) and time.time() - entry.get("at", 0) < TTL


def search(tracker, api_key: str, query: str, n: int = 3) -> tuple[list[Citation], list[dict]]:
    if not _fresh(_cache.get(query)):
        t0 = time.time()
        try:
            r = httpx.post("https://api.tavily.com/search", timeout=60,
                           headers={"Authorization": f"Bearer {api_key}"},
                           json={"query": query, "max_results": n, "search_depth": "basic", "include_domains": DOMAINS})
            r.raise_for_status()
            res = r.json().get("results", [])
        except Exception as e:
            tracker.record_tavily(query, time.time() - t0, 0, ok=False)
            raise RuntimeError(f"Tavily call failed ({type(e).__name__})") from None
        tracker.record_tavily(query, time.time() - t0, len(res))
        results = [{"title": x.get("title", ""), "url": x.get("url", ""), "content": (x.get("content") or "")[:500]}
                   for x in res if _w3c(x.get("url", ""))]   # backstop if the domain filter is ever ignored
        if not results:
            return [], []                                   # never cache an empty answer: retry next time
        _cache[query] = {"at": time.time(), "results": results}
    snippets = _cache[query]["results"][:n]
    return [Citation(title=s["title"], url=s["url"]) for s in snippets], snippets


def load_cache(path: Path) -> None:
    """Merge a saved cache, skipping expired, empty or old-format entries."""
    if path.exists():
        _cache.update({q: e for q, e in json.loads(path.read_text()).items() if _fresh(e)})


def save_cache(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({q: e for q, e in _cache.items() if _fresh(e)}, indent=1))
