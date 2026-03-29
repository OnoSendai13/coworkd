#!/usr/bin/env python3
"""
Cowork Daemon — Claude Cowork equivalent
asyncio-based plugin host + message bus subscriber
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import redis.asyncio as redis

# Add plugins to path
PLUGIN_DIR = Path(__file__).parent / "plugins"
sys.path.insert(0, str(PLUGIN_DIR))

from base import CoworkPlugin, CoworkContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("coworkd")


class CoworkDaemon:
    """Main daemon orchestrating plugins and message bus."""

    def __init__(self, config_path: str = "~/.cowork/config.yaml"):
        self.config_path = Path(config_path).expanduser()
        self.plugins: dict[str, CoworkPlugin] = {}
        self.context: Optional[CoworkContext] = None
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.running = False

    async def load_config(self) -> dict:
        """Load configuration from YAML file."""
        import yaml
        if self.config_path.exists():
            with open(self.config_path) as f:
                return yaml.safe_load(f) or {}
        return {}

    async def init_context(self, config: dict):
        """Initialize shared context."""
        workspace = Path(config.get("workspace", "~/.cowork/workspace")).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)

        self.context = CoworkContext(
            workspace=workspace,
            memory={},
            processes=[],
            files_changed=[],
            user_info=config.get("user", {}),
            redis=None,  # will be set after init_redis
        )
        log.info(f"Context initialized, workspace: {workspace}")

    async def load_plugins(self, config: dict):
        """Discover and instantiate plugins."""
        plugin_names = config.get("plugins", [
            "claude_code",
            "file_watcher",
            "process_monitor",
        ])

        for name in plugin_names:
            try:
                # Dynamic import
                mod = __import__(name, fromlist=["Plugin"])
                # Find the Plugin class (supports ClaudeCodePlugin, FileWatcherPlugin, etc.)
                plugin_cls = None
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and issubclass(attr, CoworkPlugin) and attr is not CoworkPlugin:
                        plugin_cls = attr
                        break
                if plugin_cls is None:
                    raise AttributeError(f"No Plugin class found in {name}")
                plugin = plugin_cls(self.context)
                await plugin.on_start()
                self.plugins[name] = plugin
                log.info(f"Loaded plugin: {name}")
            except Exception as e:
                log.warning(f"Failed to load plugin {name}: {e}")

    async def init_redis(self, config: dict):
        """Connect to Redis message bus."""
        redis_url = config.get("redis_url", "redis://localhost:6379")
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            await self.redis.ping()
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe("cowork:events")
            log.info(f"Connected to Redis: {redis_url}")
        except Exception as e:
            log.warning(f"Redis connection failed: {e}. Running without message bus.")
            self.redis = None

    async def handle_bus_message(self):
        """Process messages from the bus."""
        if not self.pubsub:
            return

        try:
            msg = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg and msg["type"] == "message":
                data = json.loads(msg["data"])
                plugin_name = data.get("plugin")
                if plugin_name and plugin_name in self.plugins:
                    await self.plugins[plugin_name].on_message(data)
        except Exception as e:
            log.error(f"Bus message error: {e}")

    async def save_context(self):
        """Persist context state to disk."""
        state_dir = Path("~/.cowork/state").expanduser()
        state_dir.mkdir(parents=True, exist_ok=True)

        state_file = state_dir / "context.json"
        data = {
            "memory": self.context.memory,
            "files_changed": self.context.files_changed[-100:],  # keep last 100
        }
        with open(state_file, "w") as f:
            json.dump(data, f)

    async def event_loop(self):
        """Main event processing loop."""
        log.info("Event loop started")

        while self.running:
            # Process bus messages
            await self.handle_bus_message()

            # Process plugin ticks
            for name, plugin in self.plugins.items():
                if hasattr(plugin, "on_tick"):
                    try:
                        await asyncio.wait_for(plugin.on_tick(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        log.error(f"Plugin {name} tick error: {e}")

            # Save context periodically
            if hasattr(self, "_tick_count"):
                self._tick_count += 1
            else:
                self._tick_count = 0

            if self._tick_count % 600 == 0:  # every ~minute at 100ms ticks
                await self.save_context()

            await asyncio.sleep(0.1)

    async def start(self):
        """Start the daemon."""
        log.info("Starting Cowork daemon...")

        config = await self.load_config()
        await self.init_context(config)
        await self.init_redis(config)
        # Pass redis to context so plugins can publish events
        self.context.redis = self.redis
        await self.load_plugins(config)

        self.running = True
        await self.event_loop()

    async def stop(self):
        """Stop the daemon gracefully."""
        log.info("Stopping Cowork daemon...")
        self.running = False

        # Stop all plugins
        for name, plugin in self.plugins.items():
            try:
                await plugin.on_stop()
                log.info(f"Stopped plugin: {name}")
            except Exception as e:
                log.error(f"Error stopping plugin {name}: {e}")

        # Close Redis
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()

        await self.save_context()
        log.info("Cowork daemon stopped")


async def main():
    """Entry point."""
    import signal

    daemon = CoworkDaemon()

    # Signal handlers
    loop = asyncio.get_running_loop()

    def sig_handler(sig):
        log.info(f"Received signal {sig}")
        asyncio.create_task(daemon.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: sig_handler(s))

    try:
        await daemon.start()
    except KeyboardInterrupt:
        pass
    finally:
        await daemon.stop()


if __name__ == "__main__":
    asyncio.run(main())
