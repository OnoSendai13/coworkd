"""
Screenshot plugin for Cowork

Periodic screen capture for context awareness.
Screenshots are stored locally only — never sent to external services.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from base import CoworkPlugin, CoworkContext, CoworkTool


class ScreenshotPlugin(CoworkPlugin):
    name = "screenshot"
    version = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self.enabled = False
        self.interval = 60  # seconds
        self.output_dir = Path("~/.cowork/screenshots").expanduser()
        self._capture_task: Optional[asyncio.Task] = None

    async def on_start(self):
        """Initialize screenshot capture."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Try to import screenshot library
        try:
            import mss
            self._sct = mss
            self.log.info("Screenshot (mss) available")
        except ImportError:
            try:
                import subprocess
                # Try grim (wayland) or scrot (x11)
                for cmd in ["grim", "scrot"]:
                    r = subprocess.run(["which", cmd], capture_output=True)
                    if r.returncode == 0:
                        self._cmd = cmd
                        self.log.info(f"Screenshot ({cmd}) available")
                        break
                else:
                    self.log.warning("No screenshot tool found. Install: pip install mss, or grim/scrot")
                    self._sct = None
            except Exception as e:
                self.log.warning(f"Screenshot init failed: {e}")
                self._sct = None

    async def on_stop(self):
        """Stop capture loop."""
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

    @CoworkTool(name="screenshot_capture", description="Capture a screenshot now.")
    async def capture(self, output_path: Optional[str] = None) -> str:
        """Capture a screenshot immediately."""
        if not self._sct and not hasattr(self, "_cmd"):
            return json.dumps({"error": "No screenshot tool available"})

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if output_path:
            path = Path(output_path).expanduser()
        else:
            path = self.output_dir / f"screenshot_{timestamp}.png"

        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if hasattr(self, "_sct") and self._sct:
                # mss library
                with self._sct.mss() as sct:
                    sct.shot(output=str(path))
            else:
                # grim or scrot
                import subprocess
                cmd = self._cmd
                if cmd == "grim":
                    subprocess.run([cmd, str(path)], check=True)
                elif cmd == "scrot":
                    subprocess.run([cmd, str(path)], check=True)

            self.ctx.last_screenshot = path.read_bytes()

            return json.dumps({
                "status": "captured",
                "path": str(path),
                "size": path.stat().st_size,
            })

        except Exception as e:
            return json.dumps({"error": str(e)})

    @CoworkTool(name="screenshot_start", description="Start periodic screenshots.")
    async def start(self, interval: int = 60) -> str:
        """Start periodic capture."""
        if self._capture_task and not self._capture_task.done():
            return json.dumps({"status": "already_running", "interval": self.interval})

        self.interval = interval
        self.enabled = True
        self._capture_task = asyncio.create_task(self._capture_loop())

        return json.dumps({"status": "started", "interval": interval})

    @CoworkTool(name="screenshot_stop", description="Stop periodic screenshots.")
    async def stop(self) -> str:
        """Stop periodic capture."""
        self.enabled = False
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

        return json.dumps({"status": "stopped"})

    async def _capture_loop(self):
        """Background capture loop."""
        while self.enabled:
            try:
                result = await self.capture()
                self.log.debug(f"Periodic capture: {result}")
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Capture error: {e}")
                await asyncio.sleep(self.interval)

    @CoworkTool(name="screenshot_list", description="List recent screenshots.")
    async def list_screenshots(self, limit: int = 10) -> str:
        """List recent screenshots."""
        if not self.output_dir.exists():
            return json.dumps({"screenshots": []})

        screenshots = sorted(
            self.output_dir.glob("screenshot_*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        return json.dumps({
            "screenshots": [
                {
                    "name": s.name,
                    "path": str(s),
                    "size": s.stat().st_size,
                    "modified": datetime.fromtimestamp(s.stat().st_mtime).isoformat(),
                }
                for s in screenshots
            ]
        })
