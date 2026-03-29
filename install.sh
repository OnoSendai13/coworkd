#!/usr/bin/env bash
# Coworkd Install Script
# ======================
# Sets up the Cowork daemon and optionally integrates with Hermes Agent.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/coworkd/main/install.sh | bash
#
# Or clone and run:
#   git clone https://github.com/YOUR_USER/coworkd.git ~/repos/coworkd
#   ~/repos/coworkd/scripts/install.sh
#
# Options:
#   --with-hermes    Also clone/configure Hermes fork with cowork_tools.py
#   --workspace DIR  Custom workspace directory (default: ~/.cowork/workspace)

set -e

COWORK_DIR="${COWORK_DIR:-$HOME/.cowork}"
COWORKD_REPO="${COWORKD_REPO:-$HOME/repos/coworkd}"
HERMES_FORK="${HERMES_FORK:-https://github.com/OnoSendai13/hermes-agent}"
WITH_HERMES=0

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --with-hermes) WITH_HERMES=1; shift ;;
        --workspace) COWORK_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== Coworkd Install ==="
echo "COWORK_DIR: $COWORK_DIR"
echo "COWORKD_REPO: $COWORKD_REPO"
echo "WITH_HERMES: $WITH_HERMES"

# ─── 1. Clone / update coworkd repo ───────────────────────────────────────
if [[ -d "$COWORKD_REPO/.git" ]]; then
    echo "[1/5] Updating coworkd repo..."
    git -C "$COWORKD_REPO" pull
else
    echo "[1/5] Cloning coworkd repo..."
    git clone "$COWORKD_REPO" "$COWORKD_REPO"
fi

# Symlink workspace to canonical location
mkdir -p "$COWORK_DIR"
if [[ ! -e "$COWORK_DIR/workspace" ]]; then
    ln -s "$COWORKD_REPO/workspace" "$COWORK_DIR/workspace"
fi

# ─── 2. Python dependencies ────────────────────────────────────────────────
VENV="${COWORK_DIR}/venv"
HERMES_VENV="$HOME/.hermes/hermes-agent/venv"

echo "[2/5] Checking Python dependencies..."

install_deps() {
    local venv="$1"
    "$venv/bin/pip" install --quiet psutil watchdog pyyaml aiohttp aiofiles redis mss 2>/dev/null || \
    "$venv/bin/pip" install psutil watchdog pyyaml aiohttp aiofiles redis mss
}

if [[ -d "$HERMES_VENV" ]]; then
    echo "  Using Hermes venv: $HERMES_VENV"
    install_deps "$HERMES_VENV"
else
    echo "  Creating venv at $VENV"
    python3 -m venv "$VENV"
    install_deps "$VENV"
fi

# ─── 3. Claude Code CLI ─────────────────────────────────────────────────────
echo "[3/5] Checking Claude Code CLI..."
if ! command -v claude-code &>/dev/null && ! command -v claude &>/dev/null; then
    echo "  Claude Code not found. Install: npm install -g @anthropic-ai/claude-code"
else
    # Create symlink if needed
    if command -v claude &>/dev/null && [[ ! -f "$HOME/.local/bin/claude-code" ]]; then
        mkdir -p "$HOME/.local/bin"
        ln -sf "$(which claude)" "$HOME/.local/bin/claude-code"
        echo "  Claude Code symlink created"
    fi
fi

# ─── 4. MolmoWeb ───────────────────────────────────────────────────────────
MOLMOWEB_LIB="$COWORK_DIR/lib/molmoweb"
echo "[4/5] Checking MolmoWeb..."
if [[ ! -d "$MOLMOWEB_LIB" ]]; then
    echo "  Cloning MolmoWeb..."
    mkdir -p "$COWORK_DIR/lib"
    git clone --depth=1 https://github.com/allenai/molmoweb "$MOLMOWEB_LIB"
    # Namespace package fix — add __init__.py files
    touch "$MOLMOWEB_LIB/__init__.py"
    touch "$MOLMOWEB_LIB/agent/__init__.py"
    touch "$MOLMOWEB_LIB/inference/__init__.py"
    touch "$MOLMOWEB_LIB/utils/__init__.py"
fi

# Patch molmoweb client.py if not already patched
if ! grep -q "if self.agent is not None" "$MOLMOWEB_LIB/inference/client.py" 2>/dev/null; then
    echo "  Patching molmoweb client.py (local mode agent.reset fix)..."
    sed -i 's/self\.agent\.reset()/if self.agent is not None: self.agent.reset()/g' \
        "$MOLMOWEB_LIB/inference/client.py"
fi

# ─── 5. Hermes fork (optional) ─────────────────────────────────────────────
if [[ "$WITH_HERMES" == "1" ]]; then
    echo "[5/5] Setting up Hermes fork with cowork_tools..."
    HERMES_DIR="$HOME/repos/hermes-agent"
    if [[ -d "$HERMES_DIR/.git" ]]; then
        echo "  Updating Hermes fork..."
        git -C "$HERMES_DIR" pull
    else
        echo "  Cloning Hermes fork..."
        git clone "$HERMES_FORK" "$HERMES_DIR"
    fi

    # Copy cowork_tools.py into Hermes tools/
    cp "$COWORKD_REPO/scripts/cowork_tools.py" "$HERMES_DIR/tools/cowork_tools.py"

    # Add cowork tools to toolsets.py (manual step noted)
    echo "  NOTE: Add cowork tools to toolsets.py and model_tools.py manually."
    echo "  See: $COWORKD_REPO/scripts/HERMES_INTEGRATION.md"
fi

# ─── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Install complete ==="
echo ""
echo "Cowork daemon:  python $COWORK_DIR/coworkd.py"
echo "Workspace:      $COWORK_DIR/workspace"
echo "Context file:   $COWORK_DIR/workspace/context.json"
echo ""
echo "To start the daemon:"
echo "  python $COWORK_DIR/coworkd.py"
echo ""
echo "To start on boot (systemd user service):"
echo "  cp $COWORKD_REPO/scripts/cowork.service ~/.config/systemd/user/"
echo "  systemctl --user daemon-reload"
echo "  systemctl --user enable --now cowork"
