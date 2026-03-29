"""
Process Monitor plugin for Cowork

Monitors system processes and resource usage using psutil.
Provides real-time awareness of what's running on the machine.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from base import CoworkPlugin, CoworkContext, CoworkTool


class ProcessMonitorPlugin(CoworkPlugin):
    name = "process_monitor"
    version = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self._psutil = None
        self._last_update = None

    async def on_start(self):
        """Initialize psutil."""
        try:
            import psutil
            self._psutil = psutil
            self.log.info("Process monitor active")
        except ImportError:
            self.log.warning("psutil not installed. Install with: pip install psutil")

    @CoworkTool(name="process_list", description="List running processes with CPU/RAM usage.")
    async def list_processes(self, limit: int = 20) -> str:
        """Get top processes by CPU usage."""
        if not self._psutil:
            return json.dumps({"error": "psutil not available"})

        processes = []
        for p in self._psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "cmdline"]):
            try:
                info = p.info
                if info["cpu_percent"] is None:
                    info["cpu_percent"] = 0.0
                if info["memory_percent"] is None:
                    info["memory_percent"] = 0.0
                processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Sort by CPU
        processes.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)

        # Update context
        self.ctx.processes = processes[:limit]

        return json.dumps({
            "timestamp": datetime.now().isoformat(),
            "processes": processes[:limit],
        }, indent=2)

    @CoworkTool(name="process_find", description="Find processes by name.")
    async def find_processes(self, name: str) -> str:
        """Find processes matching a name pattern."""
        if not self._psutil:
            return json.dumps({"error": "psutil not available"})

        matches = []
        for p in self._psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                pname = p.info.get("name", "")
                cmdline = " ".join(p.info.get("cmdline") or [])
                if name.lower() in pname.lower() or name.lower() in cmdline.lower():
                    matches.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return json.dumps({
            "query": name,
            "matches": matches,
            "count": len(matches),
        }, indent=2)

    @CoworkTool(name="system_resources", description="Get CPU, RAM, and disk usage summary.")
    async def system_resources(self) -> str:
        """Get system resource usage."""
        if not self._psutil:
            return json.dumps({"error": "psutil not available"})

        cpu_percent = self._psutil.cpu_percent(interval=0.1)
        cpu_count = self._psutil.cpu_count()
        memory = self._psutil.virtual_memory()
        disk = self._psutil.disk_usage("/")

        return json.dumps({
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 1),
                "used_gb": round(memory.used / (1024**3), 1),
                "percent": memory.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 1),
                "used_gb": round(disk.used / (1024**3), 1),
                "percent": round(disk.percent, 1),
            },
        }, indent=2)

    @CoworkTool(name="system_who", description="Show who is logged in and what they're doing.")
    async def system_who(self) -> str:
        """Get logged-in users and active sessions."""
        if not self._psutil:
            return json.dumps({"error": "psutil not available"})

        users = []
        for u in self._psutil.users():
            users.append({
                "name": u.name,
                "terminal": u.terminal,
                "host": u.host,
                "started": datetime.fromtimestamp(u.started).isoformat() if u.started else None,
            })

        # Also check WSL specific info
        wsl_info = {}
        try:
            # Check if running in WSL
            with open("/proc/version", "r") as f:
                version = f.read().lower()
                wsl_info["is_wsl"] = "microsoft" in version or "wsl" in version
        except Exception:
            wsl_info["is_wsl"] = False

        return json.dumps({
            "users": users,
            "wsl": wsl_info,
            "timestamp": datetime.now().isoformat(),
        }, indent=2)

    async def on_tick(self):
        """Periodically update process context."""
        # Update every 50 ticks (~5 seconds)
        if not hasattr(self, "_tick_counter"):
            self._tick_counter = 0
        self._tick_counter += 1

        if self._tick_counter % 50 == 0 and self._psutil:
            try:
                processes = []
                for p in self._psutil.process_iter(["pid", "name", "cpu_percent"]):
                    try:
                        info = p.info
                        if info["cpu_percent"] is None:
                            info["cpu_percent"] = 0.0
                        if info["cpu_percent"] > 0.1:  # Only active processes
                            processes.append(info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                self.ctx.processes = processes
                self._last_update = datetime.now()
            except Exception as e:
                self.log.debug(f"Process tick error: {e}")

    async def on_message(self, msg: dict) -> Optional[dict]:
        """Handle messages from bus."""
        if msg.get("event") == "process_query":
            query = msg.get("data", {}).get("query", "")
            if query:
                result = await self.find_processes(query)
                return {
                    "plugin": self.name,
                    "type": "process_result",
                    "content": result,
                }
        return None
