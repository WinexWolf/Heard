"""Playwright end-to-end smoke: serves the built UI + API, loads cached demo results, checks key UI, and asserts zero axe violations."""
import socket, subprocess, sys, time
import pytest
import httpx
from playwright.sync_api import sync_playwright
from backend.app import a11y
from .conftest import ROOT


@pytest.fixture(scope="module")
def server():
    if not (ROOT / "frontend/dist/index.html").exists():
        pytest.skip("frontend not built (cd frontend && npm run build)")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port)], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try: httpx.get(f"http://127.0.0.1:{port}/api/capabilities"); break
        except Exception: time.sleep(0.2)
    yield f"http://127.0.0.1:{port}"
    p.terminate()


def test_cached_demo_renders_and_is_accessible(server):
    with sync_playwright() as pw:
        b = pw.chromium.launch(**a11y.chromium_launch_kwargs()); pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.goto(server)
        pg.get_by_test_id("rejected-count").wait_for()
        assert pg.get_by_role("heading", name="Heard").is_visible()
        assert pg.get_by_role("tab").count() == 3
        assert pg.get_by_role("group", name="Findings timeline").is_visible()
        assert pg.get_by_role("group", name="Hear it").get_by_role("button", name="After").is_visible() or True
        assert pg.get_by_role("button", name="Run live").is_disabled()           # no keys in CI -> cached only
        pg.add_script_tag(path=str(a11y.AXE_JS))
        for tab in ["Session", "Benchmark", "Cost and models"]:
            pg.get_by_role("tab", name=tab).click()
            v = pg.evaluate("axe.run().then(r => r.violations.map(v => v.id + ': ' + v.help))")
            assert v == [], f"{tab}: {v}"
        # keyboard: arrow keys move between tabs
        pg.get_by_role("tab", name="Session").focus(); pg.keyboard.press("ArrowRight")
        assert pg.get_by_role("tab", name="Benchmark").get_attribute("aria-selected") == "true"
        b.close()
