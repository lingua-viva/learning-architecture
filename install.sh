#!/usr/bin/env bash
# Mission Canvas — One Command Install
# Usage: curl -fsSL https://missioncanvas.ai/install.sh | bash
# Or:    bash install.sh
set -euo pipefail

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     Mission Canvas — Install             ║"
echo "  ║     Governed AI for Professional Judgment ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# --- Check prerequisites ---
check() { command -v "$1" &>/dev/null; }

echo "Checking prerequisites..."

if ! check python3; then
    echo "ERROR: Python 3.11+ required. Install from https://python.org"
    exit 1
fi
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    echo "  Python: $PYVER ✓"
else
    echo "ERROR: Python 3.11+ required (found $PYVER)"
    exit 1
fi

if ! check git; then
    echo "ERROR: Git required."
    exit 1
fi
echo "  Git: ✓"

NODE_OK=false
if check node; then
    echo "  Node.js: $(node --version) ✓"
    NODE_OK=true
else
    echo "  Node.js: not found (optional — runtime services won't start)"
fi

# --- Clone if not already in the repo ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/MANIFEST.yaml" ]; then
    echo ""
    echo "Cloning Mission Canvas..."
    git clone https://github.com/pretendhome/mission-canvas.git
    cd mission-canvas
    SCRIPT_DIR="$(pwd)"
fi

cd "$SCRIPT_DIR"

# --- Python dependencies ---
echo ""
echo "Installing Python dependencies..."
if check uv; then
    uv pip install -e ".[dev]" 2>/dev/null || pip3 install -e ".[dev]"
else
    pip3 install -e ".[dev]" 2>/dev/null || pip3 install pyyaml redis fastapi uvicorn websockets pytest
fi

# --- Node dependencies (for runtime services) ---
if [ "$NODE_OK" = true ] && [ -f "runtime/package.json" ]; then
    echo "Installing Node.js dependencies..."
    (cd runtime && npm install --silent 2>/dev/null) || echo "  npm install skipped"
fi

# --- Create user data directories (never committed) ---
mkdir -p memory/data/notes memory/data/cron_artifacts memory/data/skill_evolution
mkdir -p config/schedules

# --- Redis (optional) ---
echo ""
if check redis-cli && redis-cli ping &>/dev/null 2>&1; then
    echo "  Redis: connected ✓"
else
    echo "  Redis: not running (optional — memory uses NDJSON fallback)"
fi

# --- Ollama (optional) ---
if check ollama; then
    if ollama list 2>/dev/null | grep -q "qwen3\|qwen2.5:7b\|phi4\|llama3"; then
        echo "  Ollama: reasoning model available ✓"
    elif ollama list 2>/dev/null | grep -q "qwen\|kimi"; then
        echo "  Ollama: model available (consider: ollama pull qwen3:8b for better reasoning)"
    else
        echo "  Ollama: installed, pull a model: ollama pull qwen3:8b"
    fi
    echo "  Tip: Set MC_REASON_MODEL=ollama/<model> to choose your reasoning model"
    echo "  Tip: Use ollama pull kimi-k2.7-code:cloud for best quality (data leaves machine)"
else
    echo "  Ollama: not found (optional — install from https://ollama.com)"
    echo "  Without Ollama, set MC_REASON_MODEL=openai/gpt-4o (needs OPENAI_API_KEY)"
fi

# --- Verify ---
echo ""
echo "Running verification..."

# Health check
python3 src/mc_cli.py health 2>/dev/null || echo "  Health check requires Ollama (optional)"

# Tests
echo ""
if [ -d "tests" ]; then
    python3 -m pytest tests/ -q --tb=line 2>/dev/null || true
fi

# --- Make mc executable and show next steps ---
chmod +x mc 2>/dev/null || true

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     Installation complete                ║"
echo "  ╠══════════════════════════════════════════╣"
echo "  ║                                          ║"
echo "  ║  Start a session:                        ║"
echo "  ║    ./mc session start                    ║"
echo "  ║                                          ║"
echo "  ║  Then use any intent:                    ║"
echo "  ║    ./mc research \"How does X work?\"       ║"
echo "  ║    ./mc protect  \"Is this privileged?\"    ║"
echo "  ║    ./mc decide   \"Should we do X or Y?\"   ║"
echo "  ║    ./mc create   \"Draft a memo\"           ║"
echo "  ║    ./mc diagnose \"Why did this fail?\"     ║"
echo "  ║    ./mc reflect  \"What did we learn?\"     ║"
echo "  ║                                          ║"
echo "  ║  End session:                            ║"
echo "  ║    ./mc session end                      ║"
echo "  ║                                          ║"
echo "  ║  System commands:                        ║"
echo "  ║    ./mc health   — system check          ║"
echo "  ║    ./mc stats    — compounding metrics   ║"
echo "  ║    ./mc eval     — run golden dataset    ║"
echo "  ║                                          ║"
echo "  ║  Web UI (after session start):           ║"
echo "  ║    http://localhost:7891                  ║"
echo "  ║                                          ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""
echo "  Add to PATH for global access:"
echo "    export PATH=\"$SCRIPT_DIR:\$PATH\""
echo ""
