#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# install-native.sh — Register the CUP Native Messaging host.
#
# This script:
#   1. Copies native_host.py to ~/.cup-bridge/
#   2. Writes the NM host manifest with correct paths
#   3. Registers it with Chrome (per-user, no admin needed)
#
# Usage:
#   bash install-native.sh [--extension-id EXTENSION_ID]
#
# After running this, the Chrome extension can launch native_host.py
# via chrome.runtime.connectNative('com.codeupipe.bridge').
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────
EXTENSION_ID="${1:-}"
INSTALL_DIR="$HOME/.cup-bridge"
HOST_NAME="com.codeupipe.bridge"

# ── Colors ───────────────────────────────────────────────────────
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

info()  { echo -e "${BLUE}[native]${NC} $1"; }
ok()    { echo -e "${GREEN}[native]${NC} $1"; }
warn()  { echo -e "${YELLOW}[native]${NC} $1"; }

# ── Parse Args ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --extension-id) EXTENSION_ID="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$EXTENSION_ID" ]]; then
  warn "No --extension-id provided."
  warn "You'll need to update the manifest after installing the extension."
  EXTENSION_ID="PLACEHOLDER_EXTENSION_ID"
fi

# ── Setup ────────────────────────────────────────────────────────
info "Installing CUP Native Messaging host..."
mkdir -p "$INSTALL_DIR"

# ── Copy native_host.py ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/native_host.py" ]]; then
  cp "$SCRIPT_DIR/native_host.py" "$INSTALL_DIR/native_host.py"
  chmod +x "$INSTALL_DIR/native_host.py"
  ok "  Copied native_host.py → $INSTALL_DIR/"
else
  warn "  native_host.py not found in $SCRIPT_DIR"
fi

# ── Find Python ─────────────────────────────────────────────────
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" &>/dev/null; then
    version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [[ "$major" -ge 3 ]] && [[ "$minor" -ge 9 ]]; then
      PYTHON="$(which "$candidate")"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  warn "Python 3.9+ not found. Using 'python3' as placeholder."
  PYTHON="python3"
fi

# ── Write NM host manifest ──────────────────────────────────────
OS="$(uname -s)"

if [[ "$OS" == "Darwin" ]]; then
  NM_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
elif [[ "$OS" == "Linux" ]]; then
  NM_DIR="$HOME/.config/google-chrome/NativeMessagingHosts"
else
  warn "Unsupported OS: $OS"
  NM_DIR="$INSTALL_DIR"
fi

mkdir -p "$NM_DIR"
NM_MANIFEST="$NM_DIR/$HOST_NAME.json"

cat > "$NM_MANIFEST" << EOF
{
  "name": "$HOST_NAME",
  "description": "CUP Platform Native Messaging Host",
  "path": "$PYTHON",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://$EXTENSION_ID/"
  ]
}
EOF

# Create a wrapper script (Chrome NM requires an executable, not a python file)
WRAPPER="$INSTALL_DIR/native_host_wrapper.sh"
cat > "$WRAPPER" << EOF
#!/usr/bin/env bash
exec "$PYTHON" "$INSTALL_DIR/native_host.py" "\$@"
EOF
chmod +x "$WRAPPER"

# Update manifest to point to wrapper
cat > "$NM_MANIFEST" << EOF
{
  "name": "$HOST_NAME",
  "description": "CUP Platform Native Messaging Host",
  "path": "$WRAPPER",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://$EXTENSION_ID/"
  ]
}
EOF

ok "  NM manifest: $NM_MANIFEST"
ok "  Host wrapper: $WRAPPER"

# ── Verify ───────────────────────────────────────────────────────
info "Verifying..."
if [[ -f "$NM_MANIFEST" ]] && [[ -f "$WRAPPER" ]]; then
  ok "  ✅ Native messaging host registered!"
  echo ""
  echo -e "${GREEN}  Host name: $HOST_NAME${NC}"
  echo -e "${GREEN}  Manifest:  $NM_MANIFEST${NC}"
  echo -e "${GREEN}  Wrapper:   $WRAPPER${NC}"
  echo -e "${GREEN}  Python:    $PYTHON${NC}"
  echo ""
  if [[ "$EXTENSION_ID" == "PLACEHOLDER_EXTENSION_ID" ]]; then
    echo -e "${YELLOW}  ⚠️  Update the extension ID in:${NC}"
    echo -e "${YELLOW}     $NM_MANIFEST${NC}"
    echo -e "${YELLOW}  After loading the extension, find its ID in chrome://extensions${NC}"
  fi
else
  warn "  Something went wrong. Check paths above."
fi
