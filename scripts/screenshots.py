"""Regenerates the README screenshots in both themes.

    .venv/bin/python scripts/screenshots.py            # → docs/screenshots/*.png

It boots the app with a temporary data folder (GUITARR_HOME) and the built-in demo data, so your own
~/.guitarr is never read or changed, and nothing starts listening or playing.
Needs Playwright with Chromium (pip install playwright && playwright install chromium).
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
PAGES = [("home", "home"), ("course", "course"), ("lesson", "lesson/major-scale"), ("rig", "rig"),
         ("chord-finder", "tools?tab=finder&mode=lead"), ("plan", "plan")]


def main() -> None:
    os.environ["GUITARR_HOME"] = tempfile.mkdtemp(prefix="guitarr-shots-")      # before importing the app
    sys.path.insert(0, str(ROOT))
    import uvicorn
    from playwright.sync_api import sync_playwright

    from guitarr.gui.server import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8790, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = "http://127.0.0.1:8790"
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("dark", "light"):
            page = browser.new_page(viewport={"width": 1280, "height": 860}, color_scheme=scheme)
            page.goto(base + "/static/index.html")
            page.evaluate("localStorage.setItem('guitarr.onboarded', '1')")
            page.request.post(base + "/api/demo")                                  # a demo song and take
            for name, route in PAGES:
                page.goto(f"{base}/#/{route}")
                page.wait_for_timeout(900)
                page.screenshot(path=str(OUT / f"{name}-{scheme}.png"))
            page.close()
        browser.close()
    server.should_exit = True
    print(f"Screenshots written to {OUT}")


if __name__ == "__main__":
    main()
