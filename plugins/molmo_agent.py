"""
MolmoWeb Agent Plugin for Cowork

Autonomous web agent powered by multimodal LMs (Molmo, GPT, Gemini).
Replaces dumb Playwright control with intelligent page understanding.

Requires: git clone https://github.com/allenai/molmoweb ~/.cowork/lib/molmoweb
Or set MOLMOWEB_ENDPOINT to point at a running model server.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from base import CoworkPlugin, CoworkContext, CoworkTool

# MolmoWeb lib path
MOLMOWEB_LIB = Path(__file__).parent.parent / "lib" / "molmoweb"

# Add to sys.path so imports resolve
if str(MOLMOWEB_LIB) not in sys.path:
    sys.path.insert(0, str(MOLMOWEB_LIB))


class Plugin(CoworkPlugin):
    name = "molmo_agent"
    version = "1.1.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self._client = None
        self._ready = False
        self._init_task: Optional[asyncio.Task] = None

    async def on_start(self):
        """Async init — clone repo if needed, then load client."""
        try:
            # Ensure molmoweb is available
            if not MOLMOWEB_LIB.exists():
                self.log.info("Cloning MolmoWeb into ~/.cowork/lib/molmoweb ...")
                import subprocess
                subprocess.run(
                    ["git", "clone", "--depth", "1",
                     "https://github.com/allenai/molmoweb",
                     str(MOLMOWEB_LIB)],
                    check=True,
                    capture_output=True,
                )
                self.log.info("MolmoWeb cloned successfully")

            # Verify required files exist
            if not (MOLMOWEB_LIB / "inference" / "client.py").exists():
                raise FileNotFoundError("inference/client.py not found in molmoweb")

            # Import the client
            from inference.client import MolmoWeb

            # Determine mode
            endpoint = os.environ.get("MOLMOWEB_ENDPOINT", "").strip()
            local = not bool(endpoint)

            if local:
                # Check for playwright
                try:
                    from playwright.async_api import async_playwright
                    self.log.info("MolmoWeb: using local Chromium (Playwright)")
                except ImportError:
                    self.log.warning(
                        "Playwright not found. Install: pip install playwright && playwright install chromium"
                    )
                    self.log.warning("Falling back to remote endpoint mode.")
                    local = False
                    endpoint = endpoint or os.environ.get("MOLMOWEB_ENDPOINT", "")

            self._client = MolmoWeb(
                endpoint=endpoint or None,
                local=local,
                keep_alive=True,
                headless=True,
                verbose=False,
            )
            self._ready = True
            self.log.info(
                f"MolmoWeb agent ready (local={local}, endpoint={endpoint or 'default'})"
            )

        except Exception as e:
            self.log.error(f"Failed to initialize MolmoWeb: {e}")
            self._ready = False

    async def on_stop(self):
        """Close the client."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._ready = False

    # ─── Tools ────────────────────────────────────────────────────────────────

    @CoworkTool(
        name="web_agent_task",
        description=(
            "Autonomous web task. Give a natural-language goal (e.g. "
            "'find the cheapest flight Paris→Rome for next Friday') and the "
            "agent will autonomously navigate, click, type and read pages to "
            "complete it. Returns a step-by-step trajectory + final answer."
        ),
    )
    async def run_task(self, task: str, max_steps: int = 15) -> str:
        """
        Run an autonomous web task.

        Args:
            task: Natural-language description of the goal.
            max_steps: Maximum browser steps (default 15). Complex tasks may
                       need more; simple ones need less.

        Returns:
            JSON with status, step count, trajectory, and final message.
        """
        if not self._ready:
            return json.dumps({
                "error": "MolmoWeb not initialized. "
                         "Check that molmoweb is cloned and playwright is installed."
            })

        try:
            traj = self._client.run(query=task, max_steps=max_steps)

            steps = []
            for i, step in enumerate(traj.steps):
                steps.append({
                    "step": i + 1,
                    "action": str(step.prediction.action) if step.prediction else None,
                    "error": step.error,
                    "page_url": step.state.page_url if step.state else None,
                })

            last = traj.steps[-1] if traj.steps else None
            final_msg = None
            if last and last.prediction and hasattr(last.prediction.action, "msg"):
                final_msg = last.prediction.action.msg

            return json.dumps({
                "status": "ok",
                "task": task,
                "steps": len(steps),
                "max_steps": max_steps,
                "hit_limit": len(steps) >= max_steps,
                "final_message": final_msg,
                "trajectory": steps,
            }, indent=2, default=str)

        except Exception as e:
            self.log.error(f"web_agent_task failed: {e}")
            return json.dumps({"error": str(e)})

    @CoworkTool(
        name="web_agent_snapshot",
        description=(
            "Capture the current browser page as an accessibility tree "
            "(axtree) plus metadata. The axtree shows the full page structure "
            "with semantic labels — much richer than raw HTML or innerText. "
            "Use this to inspect what the agent sees."
        ),
    )
    async def get_snapshot(self, url: Optional[str] = None) -> str:
        """
        Get current page state as axtree.

        Args:
            url: Optional URL to navigate to before snapshot.
                 If omitted, captures the current page.

        Returns:
            JSON with page_url, page_title, and axtree string.
        """
        if not self._ready:
            return json.dumps({"error": "MolmoWeb not initialized"})

        try:
            axtree = self._client.get_axtree(url=url)
            state = self._client.last_obs or {}

            # Extract page info from last observation
            open_pages_urls = state.get("open_pages_urls", [])
            open_pages_titles = state.get("open_pages_titles", [])
            page_idx = state.get("active_page_index", [0])[0]

            return json.dumps({
                "page_url": open_pages_urls[page_idx] if open_pages_urls else (url or ""),
                "page_title": open_pages_titles[page_idx] if open_pages_titles else "",
                "axtree_length": len(axtree),
                "axtree": axtree,
            }, indent=2)

        except Exception as e:
            self.log.error(f"get_snapshot failed: {e}")
            return json.dumps({"error": str(e)})

    @CoworkTool(
        name="web_agent_screenshot",
        description=(
            "Take a screenshot of the current (or specified) page. "
            "Useful for visual verification or sharing page state with the user."
        ),
    )
    async def take_screenshot(self, url: Optional[str] = None, full_page: bool = True) -> str:
        """
        Screenshot of the current or a given page.

        Args:
            url: Optional URL to navigate to first.
            full_page: Capture entire scrollable page (default True).

        Returns:
            JSON with path to saved PNG screenshot.
        """
        if not self._ready:
            return json.dumps({"error": "MolmoWeb not initialized"})

        try:
            from PIL import Image
            import numpy as np

            # Navigate if URL given
            if url:
                # Fresh run with the URL
                traj = self._client.run(query=f"Go to {url} and wait", max_steps=3)

            # Grab screenshot from last observation
            obs = self._client.last_obs
            if not obs or "screenshot" not in obs:
                return json.dumps({"error": "No screenshot available"})

            img: np.ndarray = obs["screenshot"]
            pil_img = Image.fromarray(img)

            out_dir = Path("~/.cowork/screenshots").expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = out_dir / f"molmo_{ts}.png"
            pil_img.save(path)

            return json.dumps({
                "status": "saved",
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "dimensions": pil_img.size,
            })

        except Exception as e:
            self.log.error(f"take_screenshot failed: {e}")
            return json.dumps({"error": str(e)})

    @CoworkTool(
        name="web_agent_status",
        description="Check if the MolmoWeb agent is initialized and ready.",
    )
    async def status(self) -> str:
        """Return plugin readiness and configuration."""
        return json.dumps({
            "ready": self._ready,
            "mode": "local" if (self._client and self._client.local) else "remote",
            "endpoint": self._client.endpoint if self._client else None,
            "molmoweb_path": str(MOLMOWEB_LIB),
            "lib_exists": MOLMOWEB_LIB.exists(),
        })
