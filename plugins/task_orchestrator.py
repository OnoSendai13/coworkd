"""
Task Orchestrator plugin for Cowork

Automates the Hermes ↔ Claude Code workflow:
1. Watches for new user goals written by Hermes to context.json
2. Executes Claude Code with the goal
3. Writes results back to context.json for Hermes to read
4. Publishes completion event to Redis

Uses polling + source tagging to avoid feedback loops.
"""

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from base import CoworkPlugin, CoworkContext, CoworkTool


# How often to check for new tasks
TASK_POLL_INTERVAL = 2.0  # seconds


class TaskOrchestratorPlugin(CoworkPlugin):
    name = "task_orchestrator"
    version = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self._poll_task: Optional[asyncio.Task] = None
        self._last_goal: str = ""
        self._last_goal_time: Optional[datetime] = None
        self._task_running: bool = False

    async def on_start(self):
        """Start polling for new tasks."""
        self.log.info("Task orchestrator active")
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def on_stop(self):
        """Stop polling."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self):
        """Poll context.json for new hermes goals."""
        while True:
            try:
                await self._check_for_tasks()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log.error(f"Poll error: {e}")
            await asyncio.sleep(TASK_POLL_INTERVAL)

    async def _check_for_tasks(self):
        """Check if Hermes wrote a new pending goal."""
        if self._task_running:
            return  # Already processing a task

        context_file = self.ctx.workspace / "context.json"
        if not context_file.exists():
            return

        try:
            with open(context_file) as f:
                ctx = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        hermes_ctx = ctx.get("hermes_context", {})
        goal = hermes_ctx.get("user_goal", "")
        status = hermes_ctx.get("goal_status", "")
        source = hermes_ctx.get("goal_source", "")

        # Only act on goals from Hermes (not from our own writes)
        if not goal or status != "pending" or source != "hermes":
            return

        # Skip if same as last goal (already processed)
        if goal == self._last_goal and self._last_goal_time:
            age = (datetime.now() - self._last_goal_time).total_seconds()
            if age < 5:
                return  # Too soon, likely a re-trigger

        self.log.info(f"New task detected: {goal[:80]}...")
        self._task_running = True

        try:
            result = await self._run_claude_code(goal)
            await self._write_result(ctx, goal, result)
        except Exception as e:
            self.log.error(f"Task execution failed: {e}")
            await self._write_error(ctx, goal, str(e))
        finally:
            self._last_goal = goal
            self._last_goal_time = datetime.now()
            self._task_running = False

    async def _run_claude_code(self, goal: str) -> dict:
        """Execute Claude Code with the given task."""
        workspace = self.ctx.workspace

        # Build Claude Code command
        cmd = [
            "claude-code", "--print",
            "--output-format", "json",
        ]

        self.log.info(f"Running Claude Code: {goal[:60]}...")

        try:
            result = subprocess.run(
                cmd,
                input=goal,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min max
                cwd=str(workspace),  # Claude Code uses CWD as project dir
            )

            if result.returncode == 0:
                try:
                    response = json.loads(result.stdout)
                    return {"status": "success", "result": response}
                except json.JSONDecodeError:
                    return {"status": "success", "result": result.stdout}
            else:
                return {
                    "status": "error",
                    "error": result.stderr or f"Exit code {result.returncode}",
                }

        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Task timed out after 300s"}
        except FileNotFoundError:
            return {"status": "error", "error": "Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _write_result(self, ctx: dict, goal: str, result: dict):
        """Write Claude Code result back to context.json."""
        context_file = self.ctx.workspace / "context.json"

        # Update hermes_context: mark goal as done
        ctx["hermes_context"]["goal_status"] = "done"
        ctx["hermes_context"]["goal_completed_at"] = datetime.now().isoformat()
        ctx["hermes_context"]["goal_result"] = result

        # Update claude_code_context with the task and result
        ctx["claude_code_context"]["last_task"] = goal
        ctx["claude_code_context"]["task_result"] = result
        ctx["claude_code_context"]["task_completed_at"] = datetime.now().isoformat()

        # Mark cowork
        ctx["cowork"] = {
            "version": "1.0.0",
            "last_update": datetime.now().isoformat(),
        }

        # Atomic write
        tmp = context_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(ctx, f, indent=2)
        tmp.rename(context_file)

        self.log.info(f"Task result written to context.json: {result.get('status')}")

        # Publish completion to Redis for Hermes gateway
        await self._publish_completion(goal, result)

    async def _write_error(self, ctx: dict, goal: str, error: str):
        """Write error to context.json."""
        context_file = self.ctx.workspace / "context.json"
        ctx["hermes_context"]["goal_status"] = "error"
        ctx["hermes_context"]["goal_error"] = error
        ctx["cowork"] = {"version": "1.0.0", "last_update": datetime.now().isoformat()}
        tmp = context_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(ctx, f, indent=2)
        tmp.rename(context_file)
        await self._publish_completion(goal, {"status": "error", "error": error})

    async def _publish_completion(self, goal: str, result: dict):
        """Publish task completion to Redis channel for Hermes gateway."""
        if not self.ctx.redis:
            self.log.debug("Redis not available, skipping publish")
            return

        try:
            message = json.dumps({
                "event": "task_completed",
                "goal": goal[:100],
                "status": result.get("status"),
                "timestamp": datetime.now().isoformat(),
            })
            await self.ctx.redis.publish("cowork:task_completed", message)
            self.log.info("Published task_completed to Redis")
        except Exception as e:
            self.log.warning(f"Redis publish failed: {e}")

    # ─── Tools ────────────────────────────────────────────────────────────────

    @CoworkTool(
        name="orchestrator_status",
        description="Get task orchestrator status: polling state, last task, current status.",
    )
    async def status(self) -> dict:
        """Return orchestrator status."""
        return {
            "polling": self._poll_task is not None and not self._poll_task.done(),
            "task_running": self._task_running,
            "last_goal": self._last_goal[:100] if self._last_goal else None,
            "last_goal_time": self._last_goal_time.isoformat() if self._last_goal_time else None,
        }

    @CoworkTool(
        name="orchestrator_run_task",
        description="Manually trigger a Claude Code task. Use this when Hermes wants to run a coding task.",
    )
    async def run_task(self, task: str) -> str:
        """
        Manually trigger a task (called from Hermes cowork_tools).
        Writes to context.json so the orchestrator picks it up.
        """
        context_file = self.ctx.workspace / "context.json"

        try:
            with open(context_file) as f:
                ctx = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            ctx = {"hermes_context": {}, "claude_code_context": {}, "cowork": {}}

        ctx["hermes_context"]["user_goal"] = task
        ctx["hermes_context"]["goal_status"] = "pending"
        ctx["hermes_context"]["goal_source"] = "hermes"
        ctx["hermes_context"]["goal_created_at"] = datetime.now().isoformat()
        ctx["cowork"] = {"version": "1.0.0", "last_update": datetime.now().isoformat()}

        with open(context_file, "w") as f:
            json.dump(ctx, f, indent=2)

        self.log.info(f"Task queued: {task[:60]}...")

        return json.dumps({
            "ok": True,
            "task": task[:100],
            "message": "Task queued. Results will be written to context.json when complete.",
        })
