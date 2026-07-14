#!/bin/sh
# Still I Rise — One Command Install
# Usage: curl -fsSL https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.sh | sh
# Tries binary first, falls back to source install if no release exists.
#
# Cloned from mission-canvas/install.sh — that script is the result of a
# month of PyInstaller/installer debugging (App Translocation, frozen-bundle
# health-check crashes, the self-spawn _MEI trap, PATH persistence). Do not
# redesign this from scratch; only adapt names/URLs/ports to this repo.
#
# Binary is named 'sir' (Still I Rise), not 'mc' — this is a fork of Mission
# Canvas and both install to ~/.local/bin/<name>. Sharing the name 'mc' would
# let whichever product installs second silently overwrite the other's
# binary on any machine that has both.
set -e

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Still I Rise — Install                 ║"
echo "  ║   AI education for refugee children      ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$ARCH" in
  x86_64|amd64) ARCH="x86_64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *) echo "  ✗ Unsupported architecture: $ARCH"; exit 1 ;;
esac

case "$OS" in
  darwin) PLATFORM="darwin"; ARCH="arm64" ;;  # Single universal binary
  linux) PLATFORM="linux" ;;
  *) echo "  ✗ Unsupported OS: $OS"; exit 1 ;;
esac

echo "  ✓ Detected: ${PLATFORM}-${ARCH}"

# Create directories. Note: the config subdir is intentionally NOT created here —
# it's created lazily on the binary-install path (below, right before providers.json
# is written) and by `git clone` on the source-fallback path. Pre-creating it here
# left ~/.still-i-rise non-empty before the source fallback's `git clone` ran,
# which made git refuse to clone into it ("already exists and is not empty").
mkdir -p "${HOME}/.local/bin"

# Pull Ollama model if ollama command is installed
pull_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    return
  fi
  # Check if daemon is running
  if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "  ⚠ Ollama installed but daemon not running."
    case "$OS" in
      darwin) echo "    → Open /Applications/Ollama.app first, then re-run install" ;;
      *)      echo "    → Run: ollama serve &" ;;
    esac
    return
  fi
  # Check if model already present
  if curl -s http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "qwen3"; then
    echo "  ✓ qwen3:8b already available"
  else
    echo "  → Pulling Ollama qwen3:8b model..."
    ollama pull qwen3:8b || true
  fi
}

# ── Try binary install first ──
BINARY="sir-${PLATFORM}-${ARCH}"
URL="https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/dist/${BINARY}"
echo "  → Downloading binary..."
TMPFILE=$(mktemp)
if curl -fsSL "$URL" -o "$TMPFILE" 2>/dev/null && [ -s "$TMPFILE" ]; then
  chmod +x "$TMPFILE"
  INSTALL_DIR="${HOME}/.local/bin"
  mv "$TMPFILE" "$INSTALL_DIR/sir"
  echo "  ✓ Installed sir to $INSTALL_DIR/sir"

  pull_ollama

  # Persist Ollama as configured provider if detected
  if command -v ollama >/dev/null 2>&1 && curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    mkdir -p "$HOME/.still-i-rise/config"
    if [ ! -f "$HOME/.still-i-rise/config/providers.json" ]; then
      cat > "$HOME/.still-i-rise/config/providers.json" << 'PROVEOF'
{
  "providers": {
    "ollama": {
      "model": "qwen3:8b",
      "verified": true
    }
  },
  "default_provider": "ollama"
}
PROVEOF
      chmod 600 "$HOME/.still-i-rise/config/providers.json"
      echo "  ✓ Connected to Ollama / qwen3:8b"
    fi
  fi

  # Put sir on PATH — write to shell profile (like Homebrew/Ollama do)
  case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
      export PATH="$INSTALL_DIR:$PATH"
      SHELL_NAME=$(basename "$SHELL")
      case "$SHELL_NAME" in
        zsh)  RC_FILE="$HOME/.zshrc" ;;
        bash) RC_FILE="$HOME/.bashrc" ;;
        *)    RC_FILE="$HOME/.profile" ;;
      esac
      if [ -f "$RC_FILE" ] && ! grep -q '.local/bin' "$RC_FILE" 2>/dev/null; then
        echo '' >> "$RC_FILE"
        echo '# Still I Rise' >> "$RC_FILE"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC_FILE"
        echo "  ✓ Added PATH to $RC_FILE"
      elif [ ! -f "$RC_FILE" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' > "$RC_FILE"
        echo "  ✓ Created $RC_FILE with PATH"
      else
        echo "  ✓ PATH already configured in $RC_FILE"
      fi
      ;;
  esac

  # Auto-start the web server. Launch `sir serve` DIRECTLY (not `sir start`) —
  # a frozen onefile that spawns itself inherits the parent's bundle dir and
  # the child dies when the parent exits. A backgrounded direct serve is
  # independent. Same fix as mission-canvas/install.sh.
  echo "  → Starting web server on http://localhost:7896 ..."
  "$INSTALL_DIR/sir" serve 7896 >/dev/null 2>&1 &

  # Poll until the server binds (frozen extract + ontology load), then open the UI
  i=0
  while [ "$i" -lt 30 ]; do
    if curl -fsS "http://127.0.0.1:7896/" >/dev/null 2>&1; then break; fi
    i=$((i + 1)); sleep 1
  done
  if [ "$i" -lt 30 ]; then
    echo "  ✓ Web UI is live"
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:7896" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then open "http://localhost:7896" >/dev/null 2>&1 &
    fi
  else
    echo "  ⚠ Web server didn't come up in time — start it later with 'sir serve'"
  fi

  # Run health check — show actual result
  echo "  → Running health check..."
  if "$INSTALL_DIR/sir" health 2>&1 | grep -q "PASS\|Health:.*100"; then
    echo "  ✓ Health check passed"
  else
    echo "  ⚠ Health check incomplete (run 'sir health' in a new terminal)"
  fi

  # Install log summary
  mkdir -p "$HOME/.still-i-rise"
  {
    echo "=== Install completed: $(date) ==="
    echo "OS: $(uname -a)"
    echo "Binary: $INSTALL_DIR/sir"
    echo "Ollama: $(command -v ollama 2>/dev/null || echo 'not found')"
    echo "Model: $(curl -s http://127.0.0.1:11434/api/tags 2>/dev/null | grep -o 'qwen3[^"]*' | head -1 || echo 'unknown')"
  } >> "$HOME/.still-i-rise/install.log"

  echo ""
  echo "  ╔══════════════════════════════════════════╗"
  echo "  ║   Installation complete!                 ║"
  echo "  ╠══════════════════════════════════════════╣"
  echo "  ║   Web UI:  http://localhost:7896          ║"
  echo "  ║   CLI:     sir health (open new terminal) ║"
  echo "  ╚══════════════════════════════════════════╝"
  echo ""
  exit 0
fi
rm -f "$TMPFILE" 2>/dev/null
echo "  ⚠ Binary not available — falling back to source install"

# ── Source install (fallback) ──
echo "  → Installing from source..."

# Check Python
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
  echo "  ✗ Python 3.11+ required. Install from https://python.org"
  exit 1
fi
echo "  ✓ Python $(python3 --version 2>&1 | cut -d' ' -f2)"

# Check Git
if ! git --version >/dev/null 2>&1; then
  echo "  ✗ Git required."
  exit 1
fi
echo "  ✓ Git"

# Clone or update to ~/.still-i-rise/
INSTALL_DIR="${HOME}/.still-i-rise"
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "  → Updating existing install..."
  (cd "$INSTALL_DIR" && git pull --quiet 2>/dev/null) || true
else
  echo "  → Cloning Still I Rise..."
  git clone --quiet --depth 1 https://github.com/lingua-viva/learning-architecture.git "$INSTALL_DIR"
fi
echo "  ✓ Source ready"

# Install Python deps (with PEP 668 break packages)
echo "  → Installing dependencies..."
cd "$INSTALL_DIR"
pip3 install --quiet --break-system-packages pyyaml redis fastapi uvicorn websockets pdfplumber sqlite-vec pytest 2>/dev/null || \
  pip3 install --quiet pyyaml redis fastapi uvicorn websockets pdfplumber sqlite-vec pytest 2>/dev/null || \
  python3 -m pip install --quiet --break-system-packages pyyaml redis fastapi uvicorn websockets pdfplumber sqlite-vec pytest 2>/dev/null || \
  echo "  ⚠ pip install failed"
echo "  ✓ Dependencies"

# Install Node.js deps if node is installed
if command -v node >/dev/null 2>&1 && [ -d "runtime" ]; then
  echo "  → Installing Node.js dependencies..."
  (cd runtime && npm install --silent 2>/dev/null) || true
fi

pull_ollama

# Verify
echo ""
python3 "$INSTALL_DIR/src/mc_cli.py" health 2>/dev/null || echo "  (Run 'sir health' to verify)"

# Auto-start web server (source mode — src/web.py is on disk)
echo "  → Starting web server on http://localhost:7896 ..."
python3 -m src.web 7896 >/dev/null 2>&1 &

# Poll until the server binds, then open the UI
i=0
while [ "$i" -lt 30 ]; do
  if curl -fsS "http://127.0.0.1:7896/" >/dev/null 2>&1; then break; fi
  i=$((i + 1)); sleep 1
done
if [ "$i" -lt 30 ]; then
  echo "  ✓ Web UI is live"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:7896" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "http://localhost:7896" >/dev/null 2>&1 &
  fi
else
  echo "  ⚠ Web server didn't come up in time — start it later with 'sir serve' (or check that dependencies installed correctly above)"
fi

# Symlink a `sir` shim on PATH so source-mode users get the same command name
cat > "${HOME}/.local/bin/sir" << SHIMEOF
#!/bin/sh
exec python3 "$INSTALL_DIR/src/mc_cli.py" "\$@"
SHIMEOF
chmod +x "${HOME}/.local/bin/sir"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Installation complete!                 ║"
echo "  ╠══════════════════════════════════════════╣"
echo "  ║   Web UI:  http://localhost:7896          ║"
echo "  ║   CLI:     sir health (open new terminal) ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
