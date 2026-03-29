# Coworkd

**Cowork daemon + plugins for Hermes Agent.** A standalone asyncio system that runs on WSL2/Ubuntu, providing process monitoring, autonomous web browsing (MolmoWeb), file watching, and Claude Code task orchestration.

**Forked from:** This repo is designed to complement a [Hermes Agent](https://github.com/nousresearch/hermes-agent) fork with integrated `cowork_tools.py`. Coworkd is the **daemon side**; Hermes with `cowork_tools.py` is the **tool interface side**. Communication between the two is via a shared `context.json` file and Redis pub/sub.

---

## What it does

```
coworkd (daemon)                          Hermes Agent (fork)
──────────────────                        ────────────────────
Plugins:                                   tools/cowork_tools.py
  task_orchestrator  ─── context.json ──  cowork_run_code_task()
  molmo_agent       ─── Redis pub/sub ──  cowork_web_task()
  process_monitor                          cowork_process_list()
  file_watcher                             cowork_system_resources()
  screenshot                               cowork_screenshot_capture()
```

The daemon runs autonomously. `cowork_tools.py` provides Hermes with tools to interact with it — reading context, triggering tasks, capturing screenshots.

---

## Quick Install

```bash
# Clone this repo
git clone https://github.com/OnoSendai13/coworkd.git ~/repos/coworkd
cd ~/repos/coworkd

# Run install (checks deps, Claude Code, MolmoWeb)
bash install.sh
```

Or with Hermes fork integration:
```bash
bash install.sh --with-hermes --workspace ~/.cowork
```

---

## Dependencies

| Dependency | Install |
|-----------|---------|
| Python 3.11+ | System |
| psutil, watchdog, redis, pyyaml, aiohttp, aiofiles, mss | `pip install ...` |
| Claude Code CLI | `npm install -g @anthropic-ai/claude-code` |
| MolmoWeb | Cloned by install script |
| Chromium (Playwright) | `playwright install chromium` |
| Redis/Valkey | Docker: `docker run -p 6379:6379 valkey/valkey:8-alpine` |
| xvfb (headless screenshot) | `apt install xvfb` |

---

## Structure

```
coworkd/
├── coworkd.py             # asyncio daemon entry point
├── config.yaml            # configuration (Redis URL, workspace, plugins)
├── plugins/              # Python plugin packages
│   ├── base.py           # CoworkPlugin ABC
│   ├── task_orchestrator.py  # Hermes ↔ Claude Code automation ★
│   ├── molmo_agent.py    # MolmoWeb autonomous web agent
│   ├── process_monitor.py
│   ├── file_watcher.py    # watchdog (inotify backend)
│   ├── screenshot.py      # mss + Xvfb fallback
│   ├── claude_code.py     # Claude Code CLI bridge
│   ├── pcloud_sync.py     # pCloud REST API
│   └── browser_control.py  # Playwright raw (legacy)
├── workspace/
│   └── context.json       # shared protocol file (gitignored)
├── scripts/
│   ├── install.sh         # install script
│   ├── cowork.service     # systemd user service
│   └── cowork_tools.py    # Hermes tool layer (copy to Hermes/tools/)
├── README.md
├── DEVELOPMENT_PLAN.md
└── .gitignore
```

---

## Starting the Daemon

```bash
# Manual
python ~/.cowork/coworkd.py

# Background (nohup)
nohup python ~/.cowork/coworkd.py > ~/.cowork/coworkd.log 2>&1 &

# Systemd (user service)
cp scripts/cowork.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cowork
```

---

## Hermes Integration

See [scripts/HERMES_INTEGRATION.md](scripts/HERMES_INTEGRATION.md) for the step-by-step.

Briefly: copy `scripts/cowork_tools.py` into your Hermes fork's `tools/` directory, add the tool names to `toolsets.py`, and add the module to `model_tools.py`.

---

## Configuration

```yaml
# ~/.cowork/config.yaml
redis_url: "redis://localhost:6379"
workspace: "~/.cowork/workspace"
plugins:
  - claude_code
  - file_watcher
  - process_monitor
  - molmo_agent
  - task_orchestrator
  # - screenshot      # uncomment if needed
  # - pcloud_sync    # uncomment if token configured
```

---

## License

MIT. Coworkd is independent software. The `cowork_tools.py` integration layer is designed for use with Hermes Agent (Anthropic's open-source agent framework).
