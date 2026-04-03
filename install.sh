#!/usr/bin/env bash
# Coworkd Install Script
# ======================
# Sets up the Cowork daemon and integrates with Hermes Agent.
#
# Usage:
#   ~/repos/coworkd/install.sh
#
# Options:
#   --workspace DIR  Custom workspace directory (default: ~/.cowork/workspace)

set -e

COWORK_DIR="${COWORK_DIR:-$HOME/.cowork}"
COWORKD_REPO="${COWORKD_REPO:-$HOME/repos/coworkd}"
HERMES_DIR="$HOME/repos/hermes-agent"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --workspace) COWORK_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== Coworkd Install ==="
echo "COWORK_DIR: $COWORK_DIR"
echo "COWORKD_REPO: $COWORKD_REPO"
echo "HERMES_DIR: $HERMES_DIR"

# ─── 1. Update coworkd repo ────────────────────────────────────────────────
if [[ -d "$COWORKD_REPO/.git" ]]; then
    echo "[1/6] Updating coworkd repo..."
    git -C "$COWORKD_REPO" pull
else
    echo "[1/6] Cloning coworkd repo..."
    git clone "https://github.com/OnoSendai13/coworkd.git" "$COWORKD_REPO"
fi

# ─── 2. Symlink workspace ─────────────────────────────────────────────────
mkdir -p "$COWORK_DIR"
if [[ ! -e "$COWORK_DIR/workspace" ]]; then
    ln -s "$COWORKD_REPO/workspace" "$COWORK_DIR/workspace"
fi

# ─── 3. Python dependencies ────────────────────────────────────────────────
VENV="$COWORK_DIR/venv"
HERMES_VENV="$HOME/.hermes/hermes-agent/venv"

echo "[3/6] Checking Python dependencies..."

install_deps() {
    local venv_python="$1"
    shift
    local pkgs="$*"
    "$venv_python" -m pip install --quiet $pkgs 2>/dev/null || \
    "$venv_python" -m pip install $pkgs
}

if [[ -d "$HERMES_VENV" ]]; then
    echo "  Using Hermes venv: $HERMES_VENV"
    install_deps "$HERMES_VENV/bin/python3" psutil watchdog pyyaml aiohttp aiofiles redis mss
else
    echo "  Creating venv at $VENV"
    python3 -m venv "$VENV"
    install_deps "$VENV/bin/python3" psutil watchdog pyyaml aiohttp aiofiles redis mss
fi

# ─── 4. Claude Code CLI ────────────────────────────────────────────────────
echo "[4/6] Checking Claude Code CLI..."
if ! command -v claude-code &>/dev/null && ! command -v claude &>/dev/null; then
    echo "  Claude Code not found. Install: npm install -g @anthropic-ai/claude-code"
else
    if command -v claude &>/dev/null && [[ ! -f "$HOME/.local/bin/claude-code" ]]; then
        mkdir -p "$HOME/.local/bin"
        ln -sf "$(which claude)" "$HOME/.local/bin/claude-code"
        echo "  Claude Code symlink created"
    fi
fi

# ─── 5. MolmoWeb ───────────────────────────────────────────────────────────
MOLMOWEB_LIB="$COWORK_DIR/lib/molmoweb"
echo "[5/6] Checking MolmoWeb..."
if [[ ! -d "$MOLMOWEB_LIB" ]]; then
    echo "  Cloning MolmoWeb..."
    mkdir -p "$COWORK_DIR/lib"
    git clone --depth=1 https://github.com/allenai/molmoweb "$MOLMOWEB_LIB"
    # Namespace package fix
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

# ─── 6. Hermes Agent (fork with cowork tools) ──────────────────────────────
echo "[6/6] Checking Hermes Agent fork..."
if [[ -d "$HERMES_DIR/.git" ]]; then
    echo "  Fetching upstream..."
    git -C "$HERMES_DIR" fetch upstream
    LOCAL=$(git -C "$HERMES_DIR" rev-parse @)
    UPSTREAM=$(git -C "$HERMES_DIR" rev-parse upstream/main)
    if [[ "$LOCAL" != "$UPSTREAM" ]]; then
        echo "  Merging upstream/main into fork..."
        git -C "$HERMES_DIR" merge upstream/main --no-edit
        echo "  Pushing to origin..."
        git -C "$HERMES_DIR" push origin main
    else
        echo "  Fork already up to date with upstream"
    fi
else
    echo "  Cloning Hermes fork..."
    git clone "https://github.com/OnoSendai13/hermes-agent.git" "$HERMES_DIR"
    git -C "$HERMES_DIR" remote add upstream "https://github.com/nousresearch/hermes-agent.git"
fi

# Install in hermes venv
if [[ -d "$HERMES_VENV" ]]; then
    echo "  Installing Hermes v0.7.0 in venv..."
    uv pip install --python "$HERMES_VENV/bin/python3" -e "$HERMES_DIR" 2>/dev/null || \
    "$HERMES_VENV/bin/python3" -m pip install -e "$HERMES_DIR"
fi

# ─── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Install complete ==="
echo ""
echo "Cowork daemon:   python $COWORK_DIR/coworkd.py"
echo "Workspace:       $COWORK_DIR/workspace"
echo "Context file:   $COWORK_DIR/workspace/context.json"
echo "Hermes:         hermes (v0.7.0 with cowork tools built-in)"
echo ""
echo "To start the daemon:"
echo "  python $COWORK_DIR/coworkd.py"
echo ""
echo "To start on boot (systemd user service):"
echo "  cp $COWORKD_REPO/scripts/cowork.service ~/.config/systemd/user/"
echo "  systemctl --user daemon-reload"
echo "  systemctl --user enable --now cowork"
