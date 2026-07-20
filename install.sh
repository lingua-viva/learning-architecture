#!/bin/sh
# Lingua Viva — One Command Install
# Usage: curl -fsSL https://raw.githubusercontent.com/lingua-viva/learning-architecture/main/install.sh | sh
# Tries binary first, falls back to source install if no release exists.
#
# Cloned from Lingua Viva install.sh — that script is the result of a
# month of PyInstaller/installer debugging (App Translocation, frozen-bundle
# health-check crashes, the self-spawn _MEI trap, PATH persistence). Do not
# redesign this from scratch; only adapt names/URLs/ports to this repo.
#
# Binary is named 'lv' (Lingua Viva). It installs to ~/.local/bin/lv.
set -e

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Lingua Viva — Install                 ║"
echo "  ║   Local-first Italian teacher workbench      ║"
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
# left ~/.lingua-viva non-empty before the source fallback's `git clone` ran,
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

# Gap 2b, SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md: a native launcher so
# restarting after a reboot/crash never requires a terminal either — only
# this initial `curl | sh` does. Idempotent: checks port 8787 for an
# already-running Lingua Viva before starting a second instance, and
# tells the user plainly (not silently) if something ELSE is holding the
# port. Written once per install; safe to re-run.
install_native_launcher() {
  mkdir -p "${HOME}/.local/bin" "${HOME}/.lingua-viva"
  cat > "${HOME}/.local/bin/lv-launch" << 'LAUNCHEOF'
#!/bin/sh
# Lingua Viva — native launcher (Gap 2b). Double-clickable via a desktop
# icon; never opens a terminal for the user. Checks whether port 8787 is
# already serving Lingua Viva before starting a second instance.
PORT=8787
HEALTH_URL="http://127.0.0.1:${PORT}/api/health"
UI_URL="http://127.0.0.1:${PORT}"
LOG="${HOME}/.lingua-viva/launch.log"
mkdir -p "${HOME}/.lingua-viva"

open_browser() {
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$UI_URL" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$UI_URL" >/dev/null 2>&1 &
  fi
}

notify() {
  echo "$(date): $1" >> "$LOG"
  if command -v notify-send >/dev/null 2>&1; then notify-send "Lingua Viva" "$1" >/dev/null 2>&1 || true; fi
  if command -v osascript >/dev/null 2>&1; then osascript -e "display notification \"$1\" with title \"Lingua Viva\"" >/dev/null 2>&1 || true; fi
}

# Already running (ours)? Just open the browser to it — don't start a
# second server instance.
RESPONSE=$(curl -fsS --max-time 2 "$HEALTH_URL" 2>/dev/null || echo "")
if [ -n "$RESPONSE" ]; then
  case "$RESPONSE" in
    *'"healthy"'*)
      notify "Lingua Viva is already running — opening your browser."
      open_browser
      exit 0
      ;;
    *)
      notify "Port ${PORT} is in use by another program — close it and try again."
      exit 1
      ;;
  esac
fi

# Nothing answered our health check. If the port is nonetheless occupied
# by something that doesn't speak it, fail loudly rather than opening a
# browser tab to the wrong thing.
if command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
  notify "Port ${PORT} is in use by another program — close it and try again."
  exit 1
fi

# Port is free — start the server.
if command -v lv >/dev/null 2>&1; then
  lv serve "$PORT" >/dev/null 2>&1 &
elif [ -f "${HOME}/.lingua-viva/src/lv_cli.py" ]; then
  ( cd "${HOME}/.lingua-viva" && python3 -m src.web "$PORT" >/dev/null 2>&1 & )
else
  notify "Couldn't find the Lingua Viva install — try re-running the installer."
  exit 1
fi

i=0
while [ "$i" -lt 30 ]; do
  if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then break; fi
  i=$((i + 1)); sleep 1
done

if [ "$i" -lt 30 ]; then
  open_browser
else
  notify "Lingua Viva didn't start in time — try again in a moment."
  exit 1
fi
LAUNCHEOF
  chmod +x "${HOME}/.local/bin/lv-launch"

  case "$OS" in
    linux)
      APPS_DIR="${HOME}/.local/share/applications"
      mkdir -p "$APPS_DIR"
      cat > "${APPS_DIR}/lingua-viva.desktop" << DESKTOPEOF
[Desktop Entry]
Type=Application
Name=Lingua Viva
Comment=Local-first Italian teacher workbench
Exec=${HOME}/.local/bin/lv-launch
Terminal=false
Categories=Education;
DESKTOPEOF
      chmod +x "${APPS_DIR}/lingua-viva.desktop"
      echo "  ✓ Desktop launcher installed (search \"Lingua Viva\" in your app menu)"
      ;;
    darwin)
      APP_DIR="${HOME}/Applications/Lingua Viva.app"
      mkdir -p "${APP_DIR}/Contents/MacOS"
      cat > "${APP_DIR}/Contents/MacOS/lingua-viva" << 'APPEOF'
#!/bin/sh
exec "$HOME/.local/bin/lv-launch"
APPEOF
      chmod +x "${APP_DIR}/Contents/MacOS/lingua-viva"
      cat > "${APP_DIR}/Contents/Info.plist" << 'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Lingua Viva</string>
  <key>CFBundleExecutable</key><string>lingua-viva</string>
  <key>CFBundleIdentifier</key><string>org.lingua-viva.lingua-viva</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
</dict>
</plist>
PLISTEOF
      echo "  ✓ App installed to ~/Applications/Lingua Viva.app"
      echo "    (first open: right-click → Open, to clear the Gatekeeper unsigned-app warning)"
      ;;
  esac
}

# ── Try binary install first ──
BINARY="lv-${PLATFORM}-${ARCH}"
URL="https://github.com/lingua-viva/learning-architecture/releases/latest/download/${BINARY}"
echo "  → Downloading binary..."
TMPFILE=$(mktemp)
if curl -fsSL "$URL" -o "$TMPFILE" 2>/dev/null && [ -s "$TMPFILE" ]; then
  chmod +x "$TMPFILE"
  INSTALL_DIR="${HOME}/.local/bin"
  mv "$TMPFILE" "$INSTALL_DIR/lv"
  echo "  ✓ Installed lv to $INSTALL_DIR/lv"

  pull_ollama

  # Persist Ollama as configured provider if detected
  if command -v ollama >/dev/null 2>&1 && curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    mkdir -p "$HOME/.lingua-viva/config"
    if [ ! -f "$HOME/.lingua-viva/config/providers.json" ]; then
      cat > "$HOME/.lingua-viva/config/providers.json" << 'PROVEOF'
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
      chmod 600 "$HOME/.lingua-viva/config/providers.json"
      echo "  ✓ Connected to Ollama / qwen3:8b"
    fi
  fi

  # Put lv on PATH — write to shell profile (like Homebrew/Ollama do)
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
        echo '# Lingua Viva' >> "$RC_FILE"
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

  install_native_launcher

  # Auto-start the web server. Launch `lv serve` DIRECTLY (not `lv start`) —
  # a frozen onefile that spawns itself inherits the parent's bundle dir and
  # the child dies when the parent exits. A backgrounded direct serve is
  # independent. Same fix as Lingua Viva install.sh.
  echo "  → Starting web server on http://localhost:8787 ..."
  "$INSTALL_DIR/lv" serve 8787 >/dev/null 2>&1 &

  # Poll until the server binds (frozen extract + ontology load), then open the UI
  i=0
  while [ "$i" -lt 30 ]; do
    if curl -fsS "http://127.0.0.1:8787/" >/dev/null 2>&1; then break; fi
    i=$((i + 1)); sleep 1
  done
  if [ "$i" -lt 30 ]; then
    echo "  ✓ Web UI is live"
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:8787" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then open "http://localhost:8787" >/dev/null 2>&1 &
    fi
  else
    echo "  ⚠ Web server didn't come up in time — start it later with 'lv serve'"
  fi

  # Run health check — show actual result
  echo "  → Running health check..."
  if "$INSTALL_DIR/lv" health 2>&1 | grep -q "PASS\|Health:.*100"; then
    echo "  ✓ Health check passed"
  else
    echo "  ⚠ Health check incomplete (run 'lv health' in a new terminal)"
  fi

  # Install log summary
  mkdir -p "$HOME/.lingua-viva"
  {
    echo "=== Install completed: $(date) ==="
    echo "OS: $(uname -a)"
    echo "Binary: $INSTALL_DIR/lv"
    echo "Ollama: $(command -v ollama 2>/dev/null || echo 'not found')"
    echo "Model: $(curl -s http://127.0.0.1:11434/api/tags 2>/dev/null | grep -o 'qwen3[^"]*' | head -1 || echo 'unknown')"
  } >> "$HOME/.lingua-viva/install.log"

  echo ""
  echo "  ╔══════════════════════════════════════════╗"
  echo "  ║   Installation complete!                 ║"
  echo "  ╠══════════════════════════════════════════╣"
  echo "  ║   Web UI:  http://localhost:8787          ║"
  echo "  ║   CLI:     lv health (open new terminal) ║"
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

# Clone or update to ~/.lingua-viva/
INSTALL_DIR="${HOME}/.lingua-viva"
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "  → Updating existing install..."
  (cd "$INSTALL_DIR" && git pull --quiet 2>/dev/null) || true
else
  echo "  → Cloning Lingua Viva..."
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
python3 -m src.lv_cli health 2>/dev/null || echo "  (Run 'lv health' to verify)"

install_native_launcher

# Auto-start web server (source mode — src/web.py is on disk)
echo "  → Starting web server on http://localhost:8787 ..."
python3 -m src.web 8787 >/dev/null 2>&1 &

# Poll until the server binds, then open the UI
i=0
while [ "$i" -lt 30 ]; do
  if curl -fsS "http://127.0.0.1:8787/" >/dev/null 2>&1; then break; fi
  i=$((i + 1)); sleep 1
done
if [ "$i" -lt 30 ]; then
  echo "  ✓ Web UI is live"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:8787" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "http://localhost:8787" >/dev/null 2>&1 &
  fi
else
  echo "  ⚠ Web server didn't come up in time — start it later with 'lv serve' (or check that dependencies installed correctly above)"
fi

# Symlink a `lv` shim on PATH so source-mode users get the same command name
cat > "${HOME}/.local/bin/lv" << SHIMEOF
#!/bin/sh
cd "$INSTALL_DIR" && exec python3 -m src.lv_cli "\$@"
SHIMEOF
chmod +x "${HOME}/.local/bin/lv"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Installation complete!                 ║"
echo "  ╠══════════════════════════════════════════╣"
echo "  ║   Web UI:  http://localhost:8787          ║"
echo "  ║   CLI:     lv health (open new terminal) ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
