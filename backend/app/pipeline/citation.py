"""Stage 3: Tavily web search to ground the WCAG citation and the ARIA pattern."""
from __future__ import annotations
import time, httpx
from ..schemas import Citation

WCAG_NAMES = {"4.1.2": "Name, Role, Value", "1.1.1": "Non-text Content", "1.3.1": "Info and Relationships",
              "2.4.4": "Link Purpose (In Context)", "2.5.3": "Label in Name", "4.1.3": "Status Messages",
              "2.4.6": "Headings and Labels", "3.3.1": "Error Identification", "2.1.1": "Keyboard"}
TECHNIQUE = {"missing_name": "icon button aria-label accessible name", "missing_alt": "img alt text",
             "missing_label": "form input label", "vague_link": "link text purpose context",
             "repeated_control": "aria-label distinguish repeated buttons", "error_not_announced": "role=alert live region error message",
             "label_in_name": "label in name aria-label visible text", "missing_state": "custom checkbox role=checkbox aria-checked",
             "div_button": "use native button element instead of div role=button", "modal_dialog": "dialog role aria-modal focus management",
             "tab_widget": "tabs pattern role=tablist tab tabpanel aria-selected", "heading_skip": "heading levels do not skip"}


def build_query(issue_type: str, wcag: str) -> str:
    name = WCAG_NAMES.get(wcag, "")
    return f"WCAG 2.2 {wcag} {name} {TECHNIQUE.get(issue_type, issue_type)} technique".replace("  ", " ").strip()


def search(tracker, api_key: str, query: str, n: int = 3) -> tuple[list[Citation], list[dict]]:
    t0 = time.time()
    try:
        r = httpx.post("https://api.tavily.com/search", timeout=60,
                       headers={"Authorization": f"Bearer {api_key}"},
                       json={"query": query, "max_results": n, "search_depth": "basic"})
        r.raise_for_status()
        res = r.json().get("results", [])
    except Exception as e:
        tracker.record_tavily(query, time.time() - t0, 0, ok=False)
        raise RuntimeError(f"Tavily call failed ({type(e).__name__})") from None
    tracker.record_tavily(query, time.time() - t0, len(res))
    cites = [Citation(title=x.get("title", ""), url=x.get("url", "")) for x in res]
    snippets = [{"title": x.get("title", ""), "url": x.get("url", ""), "content": (x.get("content") or "")[:500]} for x in res]
    return cites, snippets
