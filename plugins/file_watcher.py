"""
File Watcher plugin for Cowork

Monitors workspace files using inotify (Linux/WSE2).
Automatically triggers events on file changes.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from base import CoworkPlugin, CoworkContext, CoworkTool


# inotify flags
IN_CREATE = 0x00000100
IN_MODIFY = 0x00000002
IN_DELETE = 0x00000200
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CLOSE_WRITE = 0x00000008

EVENT_MAP = {
    IN_CREATE: "create",
    IN_MODIFY: "modify",
    IN_DELETE: "delete",
    IN_MOVED_FROM: "move_from",
    IN_MOVED_TO: "move_to",
    IN_CLOSE_WRITE: "modify",
}


class FileWatcherPlugin(CoworkPlugin):
    name = "file_watcher"
    version = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        super().__init__(ctx)
        self.watcher_task: Optional[asyncio.Task] = None
        self.watched_paths: list[Path] = []
        self.ignore_patterns: set[str] = {
            ".git", ".claude", "__pycache__",
            "node_modules", ".venv", "venv",
            "*.pyc", "*.swp", "*~",
            ".DS_Store", "Thumbs.db",
        }

    async def on_start(self):
        """Start watching the workspace."""
        self.watched_paths = [
            self.ctx.workspace,
        ]

        # Also watch configured paths from config
        config_watches = self.ctx.user_info.get("watch_paths", [])
        for p in config_watches:
            path = Path(p).expanduser()
            if path.exists():
                self.watched_paths.append(path)

        self.log.info(f"Watching {len(self.watched_paths)} paths")
        self.watcher_task = asyncio.create_task(self._watch_loop())

    async def on_stop(self):
        """Stop file watching."""
        if self.watcher_task:
            self.watcher_task.cancel()
            try:
                await self.watcher_task
            except asyncio.CancelledError:
                pass

    def _should_ignore(self, path: Path) -> bool:
        """Check if file should be ignored."""
        name = path.name
        for pattern in self.ignore_patterns:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern in str(path):
                return True
        return False

    async def _watch_loop(self):
        """
        Main file watch loop.
        Uses watchdog (inotify on Linux) for efficient file watching.
        Falls back to polling if watchdog is unavailable.
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            watchdog_available = True
        except ImportError:
            watchdog_available = False
            self.log.warning("watchdog not available, using polling fallback")

        if watchdog_available:
            await self._watchdog_watch()
        else:
            await self._polling_watch()

    async def _watchdog_watch(self):
        """Use watchdog (inotify backend on Linux) for efficient file watching."""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileSystemEvent

        class WatchdogHandler(FileSystemEventHandler):
            def __init__(handler_self, plugin):
                handler_self.plugin = plugin

            def on_any_event(handler_self, event: FileSystemEvent):
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if handler_self.plugin._should_ignore(path):
                    return
                event_type = getattr(event, 'event_type', None)
                if event_type == 'created':
                    et = 'create'
                elif event_type == 'modified':
                    et = 'modify'
                elif event_type == 'deleted':
                    et = 'delete'
                elif event_type == 'moved':
                    et = 'move_to'
                else:
                    et = event_type or 'unknown'
                asyncio.create_task(handler_self.plugin._handle_watchdog_event(path, et))

        handler = WatchdogHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.ctx.workspace), recursive=True)

        # Also watch configured paths
        for watch_path in self.watched_paths:
            if watch_path != self.ctx.workspace:
                observer.schedule(handler, str(watch_path), recursive=True)

        observer.start()
        self.log.info(f"watchdog active (inotify backend)")

        try:
            while True:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            observer.stop()
            observer.join()

    async def _handle_watchdog_event(self, path: Path, event_type: str):
        """Handle watchdog events."""
        self.ctx.files_changed.append({
            "path": str(path),
            "type": event_type,
        })
        await self.on_file_change(path, event_type)
        await self.publish("file_change", {
            "path": str(path),
            "type": event_type,
        })
        self.log.debug(f"File {event_type}: {path}")

    async def _handle_event(self, event):
        """Process an inotify event."""
        path = Path(event.path)
        name = event.name
        full_path = path / name

        if self._should_ignore(full_path):
            return

        # Get event type
        event_type = EVENT_MAP.get(event.mask, "unknown")

        # Update context
        self.ctx.files_changed.append({
            "path": str(full_path),
            "type": event_type,
        })

        # Notify plugin
        await self.on_file_change(full_path, event_type)

        # Publish to bus
        await self.publish("file_change", {
            "path": str(full_path),
            "type": event_type,
        })

        self.log.debug(f"File {event_type}: {full_path}")

    async def _polling_watch(self):
        """
        Fallback: polling-based file watching.
        Less efficient but works everywhere.
        """
        import hashlib

        last_state: dict[str, float] = {}

        while True:
            try:
                for watch_path in self.watched_paths:
                    if not watch_path.exists():
                        continue

                    for item in watch_path.rglob("*"):
                        if self._should_ignore(item):
                            continue

                        try:
                            mtime = item.stat().st_mtime
                            key = str(item)

                            if key not in last_state:
                                last_state[key] = mtime
                                await self._handle_polling_event(item, "create", last_state)
                            elif last_state[key] != mtime:
                                last_state[key] = mtime
                                await self._handle_polling_event(item, "modify", last_state)
                        except (OSError, PermissionError):
                            continue

                # Check for deletions
                deleted = [k for k in last_state if not Path(k).exists()]
                for k in deleted:
                    del last_state[k]
                    await self.publish("file_change", {"path": k, "type": "delete"})

                await asyncio.sleep(2)  # Poll every 2 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Polling error: {e}")
                await asyncio.sleep(5)

    async def _handle_polling_event(self, path: Path, event_type: str, state: dict):
        """Handle polling-based events."""
        self.ctx.files_changed.append({
            "path": str(path),
            "type": event_type,
        })
        await self.on_file_change(path, event_type)
        await self.publish("file_change", {
            "path": str(path),
            "type": event_type,
        })

    async def on_file_change(self, path: Path, event_type: str):
        """
        Override base to track file changes in context.
        Called by both inotify and polling implementations.
        """
        # Subclass should override to react to specific file types
        pass

    @CoworkTool(name="file_watcher_status", description="Get current file watcher status and recent changes.")
    async def status(self) -> dict:
        """Return watcher status."""
        return {
            "watching": [str(p) for p in self.watched_paths],
            "recent_changes": self.ctx.files_changed[-20:],
        }

    @CoworkTool(name="file_watcher_set_paths", description="Set additional paths to watch.")
    async def set_paths(self, paths: list[str]):
        """Add paths to the watch list."""
        for p in paths:
            path = Path(p).expanduser()
            if path.exists() and path not in self.watched_paths:
                self.watched_paths.append(path)
                self.log.info(f"Added watch path: {path}")
        return {"watching": [str(p) for p in self.watched_paths]}
