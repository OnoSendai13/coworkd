"""
Claude Code plugin for Cowork

Bridges Hermes with Claude Code CLI for coding tasks.
Supports both one-shot (--print) and interactive modes.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from base import CoworkPlugin, CoworkContext, CoworkTool


class ClaudeCodePlugin(CoworkPlugin):
    name = "claude_code"
    version = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self.process: Optional[asyncio.subprocess.Process] = None
        self.session_active = False
        self.workspace = ctx.workspace
        self.context_file = ctx.workspace / "context.json"

    async def on_start(self):
        """Check Claude Code availability."""
        try:
            result = subprocess.run(
                ["claude-code", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.log.info(f"Claude Code available: {result.stdout.strip()}")
        except FileNotFoundError:
            self.log.warning("Claude Code not found. Install with: npm install -g @anthropic-ai/claude-code")
        except Exception as e:
            self.log.warning(f"Claude Code check failed: {e}")

        # Ensure .claude directory exists for project settings
        claude_dir = self.workspace / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)

    async def on_stop(self):
        """Clean up Claude Code session."""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()
        self.session_active = False

    @CoworkTool(name="claude_code_ask", description="Ask Claude Code to perform a coding task. Provide the task description and optional file context.")
    async def ask(self, task: str, files: list[str] = None) -> str:
        """
        Execute a coding task using Claude Code (one-shot mode).
        """
        # Write context file for Claude Code
        context_data = {
            "task": task,
            "files": files or [],
            "memory": self.ctx.memory.get("claude_code", {}),
        }
        with open(self.context_file, "w") as f:
            json.dump(context_data, f, indent=2)

        # Build command
        cmd = [
            "claude-code", "--print",
            "--output-format", "json",
            f"--project-dir={self.workspace}",
        ]

        try:
            result = subprocess.run(
                cmd,
                input=task,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.workspace,
            )

            if result.returncode == 0:
                try:
                    response = json.loads(result.stdout)
                    # Update memory with successful context
                    self.ctx.memory.setdefault("claude_code", {})["last_task"] = task
                    return json.dumps(response, indent=2)
                except json.JSONDecodeError:
                    return result.stdout
            else:
                return json.dumps({
                    "error": result.stderr or "Unknown error",
                    "returncode": result.returncode
                }, indent=2)

        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Task timed out after 120s"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def start_interactive_session(self):
        """
        Start Claude Code in interactive mode (persistent session).
        More powerful but requires careful handling of stdin/stdout.
        """
        if self.session_active:
            return

        cmd = [
            "claude-code",
            "--dangerously-skip-permissions",
            f"--project-dir={self.workspace}",
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.workspace,
        )
        self.session_active = True
        self.log.info("Interactive Claude Code session started")

        # Start reading output in background
        asyncio.create_task(self._read_output())

    async def _read_output(self):
        """Read Claude Code output in background."""
        if not self.process or not self.process.stdout:
            return

        try:
            while self.session_active and self.process.returncode is None:
                line = await self.process.stdout.readline()
                if not line:
                    break
                self.log.debug(f"Claude Code: {line.decode().strip()}")
        except Exception as e:
            self.log.error(f"Error reading Claude Code output: {e}")
        finally:
            self.session_active = False

    async def send_to_session(self, message: str) -> str:
        """
        Send a message to an active interactive session.
        Returns the response.
        """
        if not self.session_active or not self.process:
            # Fall back to one-shot
            return await self.ask(message)

        self.process.stdin.write(f"{message}\n".encode())
        await self.process.stdin.drain()

        # For now, return empty - actual response parsing would need
        # the full Claude Code output protocol
        return json.dumps({"status": "message_sent", "session": True})

    async def on_message(self, msg: dict) -> Optional[dict]:
        """Handle messages from the bus."""
        if msg.get("event") == "code_request":
            task = msg.get("data", {}).get("task")
            files = msg.get("data", {}).get("files", [])
            result = await self.ask(task, files)
            return {
                "plugin": self.name,
                "type": "code_result",
                "content": result,
            }
        return None
