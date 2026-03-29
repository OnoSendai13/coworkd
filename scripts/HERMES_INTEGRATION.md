# Hermes Integration Guide

This guide explains how to add `cowork_tools.py` to your Hermes Agent fork.

---

## Step 1 — Copy cowork_tools.py

```bash
cp scripts/cowork_tools.py /path/to/hermes-agent/tools/cowork_tools.py
```

---

## Step 2 — Add to toolsets

In `hermes-agent/toolsets.py`, find `_HERMES_CORE_TOOLS` and add:

```python
"cowork_status", "cowork_process_list", "cowork_system_resources",
"cowork_context_read", "cowork_context_write",
"cowork_web_task", "cowork_web_snapshot",
"cowork_run_code_task",
"cowork_screenshot_capture", "cowork_screenshot_list",
```

---

## Step 3 — Discover the module

In `hermes-agent/model_tools.py`, find `_discover_tools()` and add:

```python
"tools.cowork_tools",
```

to the `_modules` list.

---

## Step 4 — Restart Hermes

The new tools will be available on the next Hermes restart.

---

## Verifying

From any Hermes session:
```
/tools cowork
```
Should list all 11 cowork tools.

---

## How the integration works

`cowork_tools.py` reads/writes `~/.cowork/workspace/context.json` directly — **the daemon does not need to be running** for basic tools (status, process_list, context read/write, screenshot capture).

The daemon **is required** for:
- `cowork_run_code_task` → task orchestration (Claude Code execution)
- `cowork_web_task` → MolmoWeb browsing
- `cowork_screenshot_capture` → Xvfb desktop capture (daemon sets up the env)

Basic tools (process list, system resources, context read/write) work standalone.

---

## Files modified in Hermes fork

| File | Change |
|------|--------|
| `tools/cowork_tools.py` | **New file** — 11 tools |
| `toolsets.py` | Added 11 tool names to `_HERMES_CORE_TOOLS` |
| `model_tools.py` | Added `"tools.cowork_tools"` to `_discover_tools()` |
