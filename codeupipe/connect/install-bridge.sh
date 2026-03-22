#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# cup-bridge install — one-liner to install spore_runner as a
# persistent background service on macOS or Linux.
#
# Usage:
#   curl -sSL https://your-site.dev/install-bridge.sh | bash
#
# Or with options:
#   curl -sSL ... | bash -s -- --port 8089 --model Qwen/Qwen3-0.6B
#
# What it does:
#   1. Checks Python 3.9+ and pip
#   2. Installs torch + transformers if missing
#   3. Downloads spore_runner.py to ~/.cup-bridge/
#   4. Installs as a background service (launchd / systemd)
#   5. Verifies health
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────
PORT="${BRIDGE_PORT:-8089}"
MODEL="${BRIDGE_MODEL:-Qwen/Qwen3-0.6B}"
RANK="${BRIDGE_RANK:-16}"
STEPS="${BRIDGE_STEPS:-30}"
INSTALL_DIR="${BRIDGE_DIR:-$HOME/.cup-bridge}"
SERVICE_NAME="cup-bridge"
QUEUE_LOCAL="--queue-local"

# ── Colors ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[bridge]${NC} $1"; }
ok()    { echo -e "${GREEN}[bridge]${NC} $1"; }
warn()  { echo -e "${YELLOW}[bridge]${NC} $1"; }
err()   { echo -e "${RED}[bridge]${NC} $1"; }

# ── Parse Args ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --port)     PORT="$2";    shift 2 ;;
    --model)    MODEL="$2";   shift 2 ;;
    --rank)     RANK="$2";    shift 2 ;;
    --steps)    STEPS="$2";   shift 2 ;;
    --dir)      INSTALL_DIR="$2"; shift 2 ;;
    --name)     SERVICE_NAME="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: install-bridge.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --port PORT     Server port (default: 8089)"
      echo "  --model MODEL   Default model (default: Qwen/Qwen3-0.6B)"
      echo "  --rank RANK     SVD rank (default: 16)"
      echo "  --steps STEPS   Training steps (default: 30)"
      echo "  --dir DIR       Install directory (default: ~/.cup-bridge)"
      echo "  --name NAME     Service name (default: cup-bridge)"
      echo "  --help          Show this help"
      exit 0
      ;;
    *) warn "Unknown option: $1"; shift ;;
  esac
done

# ── Banner ───────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}     🦴 codeupipe bridge installer                ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}     Native compute for browser dashboards       ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Check Python ─────────────────────────────────────────────────
info "Checking Python..."
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" &>/dev/null; then
    version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [[ "$major" -ge 3 ]] && [[ "$minor" -ge 9 ]]; then
      PYTHON="$candidate"
      ok "  Found $candidate ($version)"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  err "Python 3.9+ not found. Install from https://python.org"
  exit 1
fi

# ── Check / Install PyTorch ──────────────────────────────────────
info "Checking PyTorch..."
if $PYTHON -c "import torch" 2>/dev/null; then
  torch_ver=$($PYTHON -c "import torch; print(torch.__version__)")
  ok "  PyTorch $torch_ver installed"
else
  warn "  PyTorch not found. Installing..."
  $PYTHON -m pip install --quiet torch transformers
  ok "  PyTorch installed"
fi

# ── Check / Install Transformers ─────────────────────────────────
info "Checking Transformers..."
if $PYTHON -c "import transformers" 2>/dev/null; then
  tf_ver=$($PYTHON -c "import transformers; print(transformers.__version__)")
  ok "  Transformers $tf_ver installed"
else
  warn "  Transformers not found. Installing..."
  $PYTHON -m pip install --quiet transformers
  ok "  Transformers installed"
fi

# ── Create Install Directory ─────────────────────────────────────
info "Setting up $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# ── Download / Copy spore_runner.py ──────────────────────────────
info "Installing spore runner..."

# If we're in a codeupipe repo, copy from there
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPORE_CANDIDATES=(
  "$SCRIPT_DIR/../prototypes/bird-bone/spore/spore_runner.py"
  "$SCRIPT_DIR/spore_runner.py"
  "./spore/spore_runner.py"
  "./spore_runner.py"
)

SPORE_SRC=""
for candidate in "${SPORE_CANDIDATES[@]}"; do
  if [[ -f "$candidate" ]]; then
    SPORE_SRC="$candidate"
    break
  fi
done

if [[ -n "$SPORE_SRC" ]]; then
  cp "$SPORE_SRC" "$INSTALL_DIR/spore_runner.py"
  ok "  Copied from local: $SPORE_SRC"
else
  warn "  spore_runner.py not found locally"
  warn "  Copy it manually to: $INSTALL_DIR/spore_runner.py"
fi

# Copy supporting files if they exist
for support in sheets_queue.py identity.py queue_backend.gs; do
  src_dir="$(dirname "$SPORE_SRC" 2>/dev/null || echo '.')"
  if [[ -f "$src_dir/$support" ]]; then
    cp "$src_dir/$support" "$INSTALL_DIR/$support"
    ok "  Copied $support"
  fi
done

# ── Write config file ───────────────────────────────────────────
info "Writing config..."
cat > "$INSTALL_DIR/bridge.json" << EOF
{
  "name": "$SERVICE_NAME",
  "port": $PORT,
  "model": "$MODEL",
  "rank": $RANK,
  "steps": $STEPS,
  "python": "$(which "$PYTHON")",
  "install_dir": "$INSTALL_DIR",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
ok "  Config: $INSTALL_DIR/bridge.json"

# ── Install as Service ───────────────────────────────────────────
FULL_PYTHON=$(which "$PYTHON")
CMD="$FULL_PYTHON $INSTALL_DIR/spore_runner.py --port $PORT $QUEUE_LOCAL"

info "Installing as background service..."
OS="$(uname -s)"

if [[ "$OS" == "Darwin" ]]; then
  # macOS — LaunchAgent
  PLIST_DIR="$HOME/Library/LaunchAgents"
  PLIST_PATH="$PLIST_DIR/com.codeupipe.$SERVICE_NAME.plist"
  mkdir -p "$PLIST_DIR"

  cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.codeupipe.$SERVICE_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$FULL_PYTHON</string>
        <string>$INSTALL_DIR/spore_runner.py</string>
        <string>--port</string>
        <string>$PORT</string>
        <string>$QUEUE_LOCAL</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/$SERVICE_NAME.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/$SERVICE_NAME.err</string>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:$(dirname "$FULL_PYTHON")</string>
    </dict>
</dict>
</plist>
EOF

  # Unload first if already loaded
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  launchctl load "$PLIST_PATH"
  ok "  LaunchAgent installed: $PLIST_PATH"
  info "  Logs: /tmp/$SERVICE_NAME.log"
  info "  Stop:  launchctl unload $PLIST_PATH"
  info "  Start: launchctl load $PLIST_PATH"

elif [[ "$OS" == "Linux" ]]; then
  # Linux — systemd user unit
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT_PATH="$UNIT_DIR/$SERVICE_NAME.service"
  mkdir -p "$UNIT_DIR"

  cat > "$UNIT_PATH" << EOF
[Unit]
Description=codeupipe compute bridge
After=network.target

[Service]
Type=simple
ExecStart=$CMD
Restart=always
RestartSec=5
WorkingDirectory=$INSTALL_DIR
Environment=PATH=/usr/local/bin:/usr/bin:/bin:$(dirname "$FULL_PYTHON")

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable "$SERVICE_NAME"
  systemctl --user start "$SERVICE_NAME"
  ok "  systemd unit installed: $UNIT_PATH"
  info "  Logs:   journalctl --user -u $SERVICE_NAME -f"
  info "  Stop:   systemctl --user stop $SERVICE_NAME"
  info "  Start:  systemctl --user start $SERVICE_NAME"

else
  warn "  Service installation not supported on $OS"
  warn "  Run manually: $CMD"
fi

# ── Register Chrome Native Messaging Host ────────────────────────
info "Registering Chrome Native Messaging host..."
NATIVE_SCRIPT="$SCRIPT_DIR/extension/native/install-native.sh"
if [[ -f "$NATIVE_SCRIPT" ]]; then
  bash "$NATIVE_SCRIPT" 2>/dev/null && ok "  Native Messaging host registered" || warn "  NM host registration skipped (optional)"
else
  warn "  install-native.sh not found — skipping NM registration"
  warn "  Chrome extension native messaging will use HTTP fallback"
fi

# ── Verify Health ────────────────────────────────────────────────
info "Waiting for bridge to start..."
for i in $(seq 1 15); do
  if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
    ok "  ✅ Bridge is alive on port $PORT!"
    echo ""
    curl -s "http://localhost:$PORT/health" | $PYTHON -m json.tool 2>/dev/null || true
    echo ""
    break
  fi
  sleep 1
done

if ! curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
  warn "  Bridge not responding yet. Check logs:"
  warn "    cat /tmp/$SERVICE_NAME.log"
  warn "    cat /tmp/$SERVICE_NAME.err"
fi

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}  🎉 Bridge installed!                            ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Port:     $PORT                                    ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Config:   $INSTALL_DIR/bridge.json  ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Health:   http://localhost:$PORT/health           ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Any browser dashboard with bridge.js will       ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  auto-detect this compute endpoint.              ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
