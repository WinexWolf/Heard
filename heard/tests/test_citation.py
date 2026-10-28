"""Citation: criterion fixed per issue type, W3C-only results, and one Tavily call per distinct query."""
import pytest
from heard.app.llm import CostTracker
from heard.app.pipeline import citation


class FakeTavily:
    def __init__(self, results):
        self.results, self.bodies = results, []

    def __call__(self, url, json, headers, timeout):
        self.bodies.append(json)
        results = self.results

        class R:
            def raise_for_status(self): pass
            def json(self): return {"results": results}
        return R()


@pytest.fixture(autouse=True)
def empty_cache():
    citation._cache.clear(); yield; citation._cache.clear()


W3C = {"title": "Understanding SC 4.1.2: Name, Role, Value", "url": "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html", "content": "x" * 900}
APG = {"title": "Tabs Pattern | APG", "url": "https://www.w3.org/WAI/ARIA/apg/patterns/tabs/", "content": "role=tablist"}
BLOG = {"title": "10 a11y tips", "url": "https://w3.org.example.com/tips", "content": "not authoritative"}


def test_criterion_follows_the_issue_type_not_the_guess():
    assert citation.criterion("missing_name", "1.1.1") == "4.1.2"
    assert citation.criterion("error_not_announced", "") == "4.1.3"
    assert citation.criterion("other", "2.4.7") == "2.4.7"            # unknown issue: a well-formed guess is kept
    assert citation.criterion("other", "WCAG 4.1.2!") == "4.1.2"     # malformed guess falls back
    assert citation.build_query("tab_widget", "9.9.9").startswith("WCAG 2.2 4.1.2 Name, Role, Value tabs pattern")


def test_search_is_w3c_only_and_cached(monkeypatch):
    fake = FakeTavily([W3C, BLOG, APG]); monkeypatch.setattr(citation.httpx, "post", fake)
    t = CostTracker()
    cites, snippets = citation.search(t, "k", "q1")
    assert fake.bodies[0]["include_domains"] == ["w3.org"]
    assert [c.url for c in cites] == [W3C["url"], APG["url"]]          # the look-alike host is dropped
    assert len(snippets[0]["content"]) == 500
    again, _ = citation.search(t, "k", "q1")
    assert len(fake.bodies) == 1 and again == cites and t.summary()["total"]["tavily_calls"] == 1
    citation.search(t, "k", "q2")
    assert len(fake.bodies) == 2


def test_cache_survives_a_save_and_reload(monkeypatch, tmp_path):
    monkeypatch.setattr(citation.httpx, "post", FakeTavily([APG]))
    citation.search(CostTracker(), "k", "tabs")
    citation.save_cache(tmp_path / "tavily-cache.json"); citation._cache.clear()
    citation.load_cache(tmp_path / "tavily-cache.json")
    monkeypatch.setattr(citation.httpx, "post", lambda *a, **k: pytest.fail("cached query must not call Tavily"))
    cites, _ = citation.search(CostTracker(), "k", "tabs")
    assert cites[0].title == "Tabs Pattern | APG"


def test_empty_answers_are_not_cached_and_old_entries_expire(monkeypatch, tmp_path):
    fake = FakeTavily([BLOG]); monkeypatch.setattr(citation.httpx, "post", fake)   # only a non-W3C hit -> empty
    assert citation.search(CostTracker(), "k", "q") == ([], [])
    fake.results = [APG]
    assert citation.search(CostTracker(), "k", "q")[0][0].url == APG["url"] and len(fake.bodies) == 2   # retried
    citation._cache["q"]["at"] -= citation.TTL + 1                                                   # 30 days pass
    citation.search(CostTracker(), "k", "q")
    assert len(fake.bodies) == 3
    import json
    (tmp_path / "c.json").write_text(json.dumps({"old": {"at": 0, "results": [APG]}, "legacy": [APG], "empty": {"at": 9e12, "results": []}}))
    citation._cache.clear(); citation.load_cache(tmp_path / "c.json")
    assert citation._cache == {}
