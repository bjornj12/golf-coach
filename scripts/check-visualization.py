"""Headless render-check for a visualization HTML — proves it works like an artifact.

Loads the HTML via page.set_content (the same way a Claude artifact sandboxes it
through an iframe srcdoc), captures console errors / page errors, lets the
animation run, and saves a screenshot. Exit 0 if no errors.

    uv run python scripts/check-visualization.py <file.html> [screenshot.png]
    uv run python scripts/check-visualization.py --demo [screenshot.png]

Needs the [login] extra (Playwright) + a browser.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def check(html: str, shot_path: str) -> int:
    from playwright.async_api import async_playwright

    errors: list[str] = []
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1000, "height": 900})
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        await page.set_content(html, wait_until="load")
        await page.wait_for_timeout(4500)  # hangTime-scaled animations: up to 4.2s
        # sanity: canvases drew something (non-zero dimensions)
        dims = await page.evaluate(
            "Array.from(document.querySelectorAll('canvas')).map(c=>[c.width,c.height])"
        )
        await page.screenshot(path=shot_path, full_page=True)
        await browser.close()

    real_errors = [e for e in errors if e]
    print(f"canvases: {dims}")
    print(f"screenshot: {shot_path}")
    if real_errors:
        print("ERRORS/WARNINGS:")
        for e in real_errors:
            print("  -", e)
        return 1
    print("RENDER OK — no console errors or page errors.")
    return 0


def main(argv: list[str]) -> int:
    from golf_coach.visualize import _DEMO, build_html

    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--demo":
        html = build_html(_DEMO)
        shot = argv[1] if len(argv) > 1 else "viz-check.png"
    else:
        html = open(argv[0]).read()
        shot = argv[1] if len(argv) > 1 else "viz-check.png"
    return asyncio.run(check(html, shot))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
