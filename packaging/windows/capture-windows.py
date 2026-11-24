"""Build-time screenshot capture for the Windows exe."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PAGES = [("home", "home"), ("download", "download"), ("settings", "settings"), ("about", "about")]
URL = "http://127.0.0.1:3990"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 960}, device_scale_factor=1)
    for name, route in PAGES:
        page.goto(f"{URL}/#/{route}", wait_until="networkidle", timeout=30000)
        page.wait_for_selector(".page", timeout=15000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT / f"windows-{name}.png"), full_page=False)
        print(f"captured windows-{name}.png")
    browser.close()
