# Cowork Development Plan
# Claude Cowork Equivalent — WSL2 Ubuntu

> Build status: **OPERATIONAL** — Last updated: 2026-03-29

---

## Repository Structure

This repo (`coworkd`) is the **daemon + plugins** side.
It pairs with a [Hermes Agent](https://github.com/anthropics/hermes-agent) fork that includes `cowork_tools.py`.

```
github.com/YOUR_USER/coworkd/
├── coworkd.py              ← daemon entry point
├── config.yaml            ← configuration
├── plugins/               ← 9 Python plugin packages
│   ├── base.py
│   ├── task_orchestrator.py  ★ automation (Hermes → Claude Code)
│   ├── molmo_agent.py        ★ MolmoWeb browser agent
│   ├── process_monitor.py
│   ├── file_watcher.py
│   ├── screenshot.py
│   ├── claude_code.py
│   ├── pcloud_sync.py
│   └── browser_control.py
├── workspace/             ← context.json lives here (gitignored)
├── scripts/
│   ├── install.sh         ← one-shot installer
│   ├── cowork.service      ← systemd user service
│   ├── cowork_tools.py     ← copy to Hermes/tools/ for integration
│   └── HERMES_INTEGRATION.md
├── .github/workflows/ci.yml
├── README.md
├── DEVELOPMENT_PLAN.md
└── LICENSE (MIT)

github.com/YOUR_USER/hermes-agent/  (your fork)
├── tools/
│   └── cowork_tools.py    ← copied from scripts/
├── toolsets.py             ← modified (11 tool names added)
└── model_tools.py          ← modified (cowork_tools module added)
```

---

## Overview

Système multi-agent avec:
- **Hermes** comme orchestrateur / messaging gateway
- **Claude Code** comme agent de codage
- **Plugins** pour l'interaction machine (fichiers, processus, browser, etc.)
- **pCloud** pour la synchronisation cloud
- Tout tourne sur **WSL2 Ubuntu**

---

## Architecture

```
WSL2 Ubuntu
│
├── coworkd (daemon asyncio, PID actif)        # Plugin host + Redis bus
│   ├── Plugin Engine                           # Hot-reload Python plugins
│   ├── Redis Bus (Valkey 7.2.4)               # Inter-plugin + Hermes comm
│   ├── Context Watcher (watchdog)             # inotify + polling fallback
│   └── Task Orchestrator                      # Hermes ↔ Claude Code automation ★
│
├── Plugins (~/.cowork/plugins/)
│   ├── base.py                    # ABC CoworkPlugin ✓
│   ├── claude_code.py            # Claude Code CLI bridge ✓
│   ├── file_watcher.py           # watchdog (inotify backend) ✓
│   ├── process_monitor.py        # psutil system info ✓
│   ├── task_orchestrator.py       # Workflow automation ★ ✓
│   ├── molmo_agent.py            # MolmoWeb / GPT / Gemini ★ ✓
│   ├── pcloud_sync.py            # pCloud REST API ✓
│   ├── screenshot.py             # mss + Xvfb fallback ✓
│   └── browser_control.py        # Playwright headless (legacy)
│
├── Hermes Agent (~/.hermes/hermes-agent/)
│   └── tools/cowork_tools.py     # 11 outils Hermès exposés ★
│
├── Claude Code CLI (NVM)          # v2.1.87 (claude → claude-code)
└── n8n (Docker)                   # Automation (port 5678)
```

---

## Phase 1 — Core Daemon ✓ DONE

### Files Created

- [x] `~/.cowork/coworkd.py` — Main daemon (asyncio, plugin loader, redis bus)
- [x] `~/.cowork/config.yaml` — Configuration
- [x] `~/.cowork/plugins/base.py` — CoworkPlugin ABC
- [x] `~/.cowork/plugins/__init__.py`

### Bugs Fixed

- [x] **Plugin class discovery** — coworkd.py cherchait `mod.Plugin` (inexistant).
  Corrigé: auto-détection des classes `*Plugin` via `issubclass`.
- [x] **Redis URL** — `localhost:6379` → `10.255.255.254:6379` (Docker bridge WSL)
- [x] **Claude Code CLI** — binary s'appelle `claude` (NVM), symlink créé
  `~/.local/bin/claude-code` → `claude`

---

## Phase 2 — Core Plugins ✓ DONE

### 2.1 claude_code.py ✓

**Status:** Functional. v2.1.87 détecté et intégré.

**Features:**
- `ask(task, files)` — One-shot Claude Code execution
- `start_interactive_session()` — Persistent session
- `send_to_session(msg)` — Send to active session

### 2.2 file_watcher.py ✓

**Status:** Functional. watchdog (backend inotify).

**Bug Fixed:**
- [x] `inotify.aio` → `watchdog.observers.Observer` (inotify package n'a pas de submodule `aio`)

**Features:**
- watchdog sur workspace paths
- Automatic fallback à polling
- Ignore patterns pour common dirs
- Event publishing to Redis bus

### 2.3 process_monitor.py ✓

**Status:** Functional, provides 4 tools.

**Tools exposed:**
- `process_list` — Top processes by CPU
- `process_find` — Search by name/cmdline
- `system_resources` — CPU/RAM/disk summary
- `system_who` — Logged-in users + WSL detection

### 2.4 task_orchestrator.py ★ NEW

**Status:** Fully operational (2026-03-29).

**Workflow:**
1. Poll `context.json` toutes les 2s pour `goal_status=pending` + `goal_source=hermes`
2. Exécute `claude-code --print --output-format=json` dans le workspace
3. Écrit résultat dans `claude_code_context.task_result`
4. Marque `goal_status=done`
5. Publish `cowork:task_completed` sur Redis

**Tools exposed:**
- `orchestrator_status` — polling state, last task, running status
- `orchestrator_run_task` — queue une tâche manuellement

---

## Phase 3 — Enhanced Plugins

### 3.1 screenshot.py ✓

**Status:** Functional (2026-03-29). mss + Xvfb fallback.

**Features:**
- Full screen capture via `mss` (X11) ou `xvfb-run` (headless WSL)
- Periodic capture mode (interval configurable)
- JPEG/PNG compression
- Local storage only (privacy)
- **Tools:** `screenshot_capture`, `screenshot_start`, `screenshot_stop`, `screenshot_list`

**Dépendances:**
- `mss` (Python package) — installé
- `xvfb-run` (system package) — disponible

### 3.2 browser_control.py (legacy)

Status: Replaced by `molmo_agent.py` (AI-powered browsing).

### 3.3 molmo_agent.py ★ ✓

**Status:** Fully functional. Chromium local via Playwright. MolmoWeb cloned + patched.

**Bug Fixed (2026-03-29):**
- `inference/client.py` — `fresh_run()` et `continue_run()` appelaient `self.agent.reset()` même quand `self.agent` était `None` (mode local sans endpoint). Patché avec `if self.agent is not None: self.agent.reset()`.

**Tools exposed:**
- `web_agent_task` — autonomous navigation
- `web_agent_snapshot` — axtree + page info
- `web_agent_screenshot` — PNG screenshot
- `web_agent_status` — readiness check

**Installation:** Cloned automatically à `~/.cowork/lib/molmoweb` + `__init__.py` files ajoutés (namespace package flat-layout):
```bash
# Automatic on first start, or manually:
git clone --depth=1 https://github.com/allenai/molmoweb ~/.cowork/lib/molmoweb
touch ~/.cowork/lib/molmoweb/__init__.py
touch ~/.cowork/lib/molmoweb/agent/__init__.py
touch ~/.cowork/lib/molmoweb/inference/__init__.py
touch ~/.cowork/lib/molmoweb/utils/__init__.py

# Playwright (for molmo_agent):
~/.hermes/hermes-agent/venv/bin/pip3 install playwright
~/.hermes/hermes-agent/venv/bin/playwright install chromium
```

### 3.4 pcloud_sync.py (TODO)

**Features:** Dual-mode (local mount + REST API). OAuth token flow still manual.

---

## Phase 4 — Hermes Integration ✓ DONE (2026-03-29)

### 4.1 Tools Registered

**File:** `~/.hermes/hermes-agent/tools/cowork_tools.py` (11 outils)

```
cowork_status              — Daemon, Redis, Claude Code, context
cowork_process_list       — Top processes by CPU/RAM
cowork_system_resources    — CPU, RAM, disk, network
cowork_context_read        — Read shared context.json
cowork_context_write       — Write to shared context.json
cowork_run_code_task      — Queue Claude Code task (async) ★
cowork_web_task           — MolmoWeb autonomous web agent
cowork_web_snapshot       — Current page accessibility tree
cowork_screenshot_capture — Screen capture (mss + Xvfb)
cowork_screenshot_list    — List recent screenshots
```

### 4.2 Integration Points

- `~/.hermes/hermes-agent/model_tools.py` — `tools.cowork_tools` in `_discover_tools()`
- `~/.hermes/hermes-agent/toolsets.py` — cowork tools in `_HERMES_CORE_TOOLS`

### 4.3 Context Protocol

**File:** `~/.cowork/workspace/context.json`

```json
{
  "hermes_context": {
    "user_goal": "...",
    "goal_status": "pending|done|error",
    "goal_source": "hermes",
    "goal_created_at": "ISO timestamp",
    "goal_result": { "status": "success|error", ... },
    "goal_completed_at": "ISO timestamp"
  },
  "claude_code_context": {
    "last_task": "...",
    "task_result": { ... },
    "task_completed_at": "ISO timestamp"
  },
  "cowork": {
    "version": "1.0.0",
    "last_update": "ISO timestamp"
  }
}
```

**Workflow:**
1. User → Hermes: "code this project"
2. Hermes → `cowork_run_code_task(task="code this project")`
   → writes: `goal_status=pending`, `goal_source=hermes`
3. task_orchestrator detects pending → runs Claude Code
4. task_orchestrator writes: `goal_status=done`, `task_result={...}`
5. Hermes polls `cowork_context_read` → `goal_status=done` → responds to user

---

## Phase 5 — Claude Code ↔ Hermes Context Sharing ✓ DONE

### 5.1 Context File Protocol ✓

Implemented via `context.json` (Phase 4.3).

### 5.2 Workflow ✓

Automated via task_orchestrator plugin.

---

## Setup Instructions

### Prerequisites

```bash
# Python deps (Hermes venv)
~/.hermes/hermes-agent/venv/bin/pip install psutil inotify redis watchdog pyyaml aiohttp aiofiles mss

# Claude Code CLI (via NVM — already installed)
# Symlink already created: ~/.local/bin/claude-code → ~/.nvm/.../bin/claude

# Redis (Valkey on Docker — already running)
# Accessible at: redis://10.255.255.254:6379

# MolmoWeb (auto-clone on first start, or manually):
git clone --depth=1 https://github.com/allenai/molmoweb ~/.cowork/lib/molmoweb

# Playwright (for molmo_agent):
~/.hermes/hermes-agent/venv/bin/pip install playwright
~/.hermes/hermes-agent/venv/bin/playwright install chromium
```

### Configuration

1. Edit `~/.cowork/config.yaml` if needed (Redis URL, workspace path)

2. Optional: pCloud OAuth token:
   ```bash
   echo "YOUR_PCLOUD_OAUTH_TOKEN" > ~/.cowork/pcloud_token
   chmod 600 ~/.cowork/pcloud_token
   ```

### Launch

```bash
# Start daemon
python ~/.cowork/coworkd.py

# Or as systemd service (already configured in ~/.config/systemd/user/):
systemctl --user start cowork
systemctl --user status cowork
```

---

## Testing

```bash
# Test daemon startup
python ~/.cowork/coworkd.py
# Expected: loads 5 plugins, connects to Redis, starts event loop

# Test Claude Code
claude-code --version
# Expected: 2.1.87 (Claude Code)

# Test context protocol
# In Hermes: use cowork_run_code_task, then poll cowork_context_read

# Test screenshot
xvfb-run -a python -c "import mss; sct = mss.mss(); sct.shot(output='/tmp/test.png'); print('OK')"

# Test molmo_agent
~/.hermes/hermes-agent/venv/bin/python -c "
import sys; sys.path.insert(0, '~/.cowork/plugins');
sys.path.insert(0, '~/.cowork/lib/molmoweb');
from plugins.molmo_agent import Plugin;
print('OK')
"
```

---

## Current System Status (2026-03-29)

| Component | Status | Notes |
|-----------|--------|-------|
| Daemon (coworkd) | **RUNNING** | PID actif, 5 plugins loaded |
| Redis/Valkey | **OK** | `redis://10.255.255.254:6379`, pub/sub verified |
| Claude Code CLI | **OK** | v2.1.87, `--print --json` mode works |
| file_watcher | **OK** | watchdog (inotify backend) active |
| process_monitor | **OK** | psutil, 4 tools exposed |
| task_orchestrator | **OK** | Poll loop, Claude Code integration verified |
| molmo_agent | **OK** | Chromium local via Playwright |
| screenshot | **OK** | mss + Xvfb fallback |
| Hermes cowork_tools | **OK** | 11 tools registered in toolset |
| context.json protocol | **OK** | pending → done, Hermes ↔ Claude Code verified |
| pcloud_sync | **NOT LOADED** | Token not configured (commented in config) |

---

## Next Actions

- [ ] **pcloud_sync** — Configure OAuth token for pCloud
- [ ] **Desktop notifications** — WSL2 notification daemon setup
- [ ] **GPU monitoring** — `nvidia-smi` integration in process_monitor
- [ ] **Browser notifications** — Proactive suggestions from task_orchestrator
- [ ] **Systemd service** — Install as user systemd service for auto-start on boot
