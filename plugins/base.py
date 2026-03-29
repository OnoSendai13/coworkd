"""
Cowork Plugin Base Class

All plugins must inherit from CoworkPlugin and implement the required methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import logging

log = logging.getLogger("cowork.plugins")


@dataclass
class CoworkContext:
    """Shared context passed to all plugins."""
    workspace: Path
    memory: dict
    processes: list
    files_changed: list
    last_screenshot: Optional[bytes] = None
    user_info: dict = field(default_factory=dict)

    # Runtime state
    redis: Any = None  # redis client for publishing
    hermes_inject: Any = None  # callback to inject into Hermes


@dataclass
class CoworkMessage:
    """Message format for plugin communication."""
    plugin: str
    event: str
    data: dict = field(default_factory=dict)
    timestamp: float = 0.0


class CoworkPlugin(ABC):
    """Abstract base class for Cowork plugins."""

    name: str = "base"
    version: str = "1.0.0"

    def __init__(self, ctx: CoworkContext):
        self.ctx = ctx
        self.log = logging.getLogger(f"cowork.{self.name}")
        self._running = False

    @abstractmethod
    async def on_start(self):
        """Called when plugin is loaded. Initialize resources here."""
        pass

    async def on_stop(self):
        """Called when daemon stops. Cleanup resources here."""
        self._running = False

    async def on_message(self, msg: dict) -> Optional[dict]:
        """
        Handle incoming message from message bus.
        Return a dict to inject into Hermes context, or None.
        """
        return None

    async def on_file_change(self, path: Path, event_type: str):
        """
        Called when a watched file changes.
        event_type: 'create', 'modify', 'delete', 'move'
        """
        pass

    async def on_tick(self):
        """
        Called periodically (every ~100ms) for plugins that need polling.
        Keep this fast — avoid blocking.
        """
        pass

    async def publish(self, event: str, data: dict):
        """Publish an event to the message bus."""
        if self.ctx.redis:
            import json
            msg = {
                "plugin": self.name,
                "event": event,
                "data": data,
            }
            await self.ctx.redis.publish("cowork:events", json.dumps(msg))

    def inject_to_hermes(self, data: dict):
        """
        Inject data into Hermes context.
        This callback is set by the daemon.
        """
        if self.ctx.hermes_inject:
            self.ctx.hermes_inject(self.name, data)


class CoworkTool:
    """
    Decorator to expose plugin methods as tools to Hermes.
    Tools are automatically registered when the plugin loads.
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    def __call__(self, func):
        func._cowork_tool = True
        func._tool_name = self.name
        func._tool_description = self.description
        return func
