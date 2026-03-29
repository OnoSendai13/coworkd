"""
Browser Control plugin for Cowork

Headless browser control via Playwright.
Enables web navigation, content extraction, screenshots.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from base import CoworkPlugin, CoworkContext, CoworkTool


class BrowserPlugin(CoworkPlugin):
    name = "browser_control"
    version = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self._playwright = None
        self._browser = None
        self._page = None
        self._initialized = False

    async def on_start(self):
        """Initialize Playwright."""
        try:
            from playwright.async_api import async_playwright
            self._playwright = async_playwright
            self.log.info("Playwright available")
        except ImportError:
            self.log.warning(
                "Playwright not installed. Install with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

    async def on_stop(self):
        """Close browser."""
        if self._browser:
            await self._browser.close()

    async def _ensure_browser(self):
        """Lazy init browser."""
        if not self._playwright:
            return False

        if not self._browser:
            p = await self._playwright.start()
            self._browser = await p.chromium.launch(headless=True)
            self._initialized = True

        if not self._page:
            self._page = await self._browser.new_page()

        return True

    @CoworkTool(name="browser_navigate", description="Navigate to a URL.")
    async def navigate(self, url: str) -> str:
        """Navigate to URL and return page content."""
        if not await self._ensure_browser():
            return json.dumps({"error": "Playwright not available"})

        try:
            await self._page.goto(url, wait_until="networkidle", timeout=30000)
            title = await self._page.title()

            return json.dumps({
                "status": "loaded",
                "url": url,
                "title": title,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="browser_screenshot", description="Take a screenshot of current page.")
    async def screenshot(self, output_path: Optional[str] = None) -> str:
        """Take a screenshot."""
        if not await self._ensure_browser():
            return json.dumps({"error": "Browser not available"})

        if not output_path:
            output_path = f"~/.cowork/screenshots/browser_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            await self._page.screenshot(path=path, full_page=True)
            return json.dumps({
                "status": "captured",
                "path": str(path),
                "size": path.stat().st_size,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="browser_content", description="Get page text content.")
    async def content(self, max_length: int = 10000) -> str:
        """Get page text content."""
        if not await self._ensure_browser():
            return json.dumps({"error": "Browser not available"})

        try:
            text = await self._page.inner_text("body")
            if len(text) > max_length:
                text = text[:max_length] + "..."
            return json.dumps({
                "content": text,
                "length": len(text),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="browser_click", description="Click an element by selector.")
    async def click(self, selector: str) -> str:
        """Click element by CSS selector."""
        if not await self._ensure_browser():
            return json.dumps({"error": "Browser not available"})

        try:
            await self._page.click(selector, timeout=5000)
            return json.dumps({"status": "clicked", "selector": selector})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="browser_type", description="Type text into an input field.")
    async def type(self, selector: str, text: str, submit: bool = False) -> str:
        """Type into element and optionally submit."""
        if not await self._ensure_browser():
            return json.dumps({"error": "Browser not available"})

        try:
            await self._page.fill(selector, text)
            if submit:
                await self._page.press(selector, "Enter")
            return json.dumps({
                "status": "typed",
                "selector": selector,
                "text": text,
                "submitted": submit,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="browser_evaluate", description="Run JavaScript on the page.")
    async def evaluate(self, script: str) -> str:
        """Execute JavaScript on page."""
        if not await self._ensure_browser():
            return json.dumps({"error": "Browser not available"})

        try:
            result = await self._page.evaluate(script)
            return json.dumps({"result": result}, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})
