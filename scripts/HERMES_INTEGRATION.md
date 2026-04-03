# Hermes Integration Guide

The `cowork_tools` integration is **already included** in the Hermes Agent fork
(`OnoSendai13/hermes-agent`). After syncing the fork, the 10 cowork tools are
automatically registered and available — no manual steps required.

---

## Quick Setup (Already Done)

Your fork already has the integration. To update:

```bash
cd ~/repos/hermes-agent
git fetch upstream
git merge upstream/main
git push origin main
```

Then restart Hermes. The tools are in `_HERMES_CORE_TOOLS` and always enabled.

---

## What Was Integrated

| File | Change |
|------|--------|
| `tools/cowork_tools.py` | New — 10 tools (status, process list, context, web, screenshot, delegation) |
| `toolsets.py` | 10 tool names added to `_HERMES_CORE_TOOLS` |
| `model_tools.py` | `"tools.cowork_tools"` added to `_discover_tools()` |

---

## Verifying

```bash
hermes tools list    # No separate "cowork" toolset — tools are always-on (core)
hermes status        # Shows Hermes + Cowork status
```

Or in any chat session, the tools are available directly:
- `/tools` shows `cowork_status` among available tools

---

## How the Integration Works

`cowork_tools.py` reads/writes `~/.cowork/workspace/context.json` directly — **the
daemon does not need to be running** for basic tools (status, process_list,
context read/write, screenshot capture).

The daemon **is required** for:
- `cowork_run_code_task` → task orchestration (Claude Code execution)
- `cowork_web_task` → MolmoWeb browsing
- `cowork_screenshot_capture` → Xvfb desktop capture (daemon sets up the env)

Basic tools (process list, system resources, context read/write) work standalone.

---

## Coworkd vs Hermes-Agent

```
coworkd (this repo)            Hermes fork (hermes-agent)
────────────────────           ───────────────────────────
coworkd.py daemon              tools/cowork_tools.py
plugins/                       10 registered tools in
  molmo_agent.py                 _HERMES_CORE_TOOLS
  task_orchestrator.py
  screenshot.py
  process_monitor.py
  pcloud_sync.py
  claude_code.py
  file_watcher.py
  browser_control.py
  base.py
```

Communication: `cowork_tools.py` <-> `~/.cowork/workspace/context.json` <-> daemon.
