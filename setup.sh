#!/usr/bin/env bash
# Mission Canvas — Setup & Launch
# Installs dependencies, starts services, opens browser.
# Usage: ./setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║     Mission Canvas — Setup & Launch      ║"
echo "  ║     Governed AI for Professional Judgment ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# --- Prerequisites ---
check() { command -v "$1" &>/dev/null; }

echo "Checking prerequisites..."
check python3 && echo "  Python: $(python3 --version 2>&1 | cut -d' ' -f2)" || { echo "ERROR: Python 3.11+ required"; exit 1; }
check node && echo "  Node: $(node --version)" || echo "  WARNING: Node.js not found (hub/broker won't start)"
check git && echo "  Git: $(git --version | cut -d' ' -f3)" || { echo "ERROR: Git required"; exit 1; }

# --- Python deps ---
echo ""
echo "Installing Python dependencies..."
if check uv; then
    uv pip install -e ".[dev]" 2>/dev/null || pip install pyyaml redis pytest 2>/dev/null
else
    pip install pyyaml redis pytest 2>/dev/null || pip install --user pyyaml redis pytest 2>/dev/null
fi

# --- Node deps ---
if check node && [ -d "runtime" ]; then
    echo "Installing Node.js dependencies..."
    cd runtime && npm install --silent 2>/dev/null; cd ..
fi

# --- Data dirs ---
mkdir -p memory/data/notes memory/data/cron_artifacts config/schedules knowledge/proposals

# --- Redis ---
echo ""
REDIS_PID=""
if check redis-cli && redis-cli ping &>/dev/null 2>&1; then
    echo "Redis: already running"
elif [ -f "$HOME/.local/bin/redis-server" ]; then
    echo "Starting Redis..."
    "$HOME/.local/bin/redis-server" --daemonize yes --dir "$SCRIPT_DIR/memory/data" --port 6379 2>/dev/null
    echo "Redis: started"
else
    echo "Redis: not found (using in-memory fallback)"
fi

# --- Run tests ---
echo ""
echo "Running tests..."
python3 -m pytest tests/ -q --tb=line 2>/dev/null || echo "  (Some tests need additional deps)"

# --- Start services ---
echo ""
echo "Starting services..."

# 1. API Server (Python pipeline on :7891)
echo "  Starting API server on :7891..."
python3 src/api_server.py 7891 &
API_PID=$!
sleep 2

# 2. Broker (Node.js message bus on :7899) — only if not already running
if check node; then
    if curl -s http://127.0.0.1:7899/health &>/dev/null; then
        echo "  Broker: already running on :7899"
    else
        echo "  Starting broker on :7899..."
        cd runtime && node broker/index.mjs &
        BROKER_PID=$!
        cd ..
        sleep 1
    fi

    # 3. Hub (Node.js web UI on :7890)
    if curl -s http://127.0.0.1:7890 &>/dev/null; then
        echo "  Hub: already running on :7890"
    else
        echo "  Starting hub on :7890..."
        cd runtime && node hub/server.mjs &
        HUB_PID=$!
        cd ..
        sleep 1
    fi
fi

# --- Verify ---
echo ""
echo "Verifying services..."
curl -s http://127.0.0.1:7891/api/health &>/dev/null && echo "  API server:  http://127.0.0.1:7891 ✓" || echo "  API server:  not responding"
curl -s http://127.0.0.1:7899/health &>/dev/null && echo "  Broker:      http://127.0.0.1:7899 ✓" || echo "  Broker:      not running"
curl -s http://127.0.0.1:7890 &>/dev/null && echo "  Hub:         http://127.0.0.1:7890 ✓" || echo "  Hub:         not running"

# --- Health ---
echo ""
python3 src/mc_cli.py health 2>/dev/null || true

# --- Open browser ---
echo ""
if check xdg-open; then
    echo "Opening browser..."
    xdg-open http://127.0.0.1:7890 2>/dev/null &
elif check open; then
    open http://127.0.0.1:7890 2>/dev/null &
fi

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║     Mission Canvas is running                    ║"
echo "  ╠══════════════════════════════════════════════════╣"
echo "  ║                                                  ║"
echo "  ║  Web UI:     http://localhost:7890                ║"
echo "  ║  API:        http://localhost:7891/api/query      ║"
echo "  ║  Broker:     http://localhost:7899                ║"
echo "  ║                                                  ║"
echo "  ║  CLI:        mc health | mc stats | mc research   ║"
echo "  ║  Stop:       mc stop                              ║"
echo "  ║                                                  ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop all services."

# Wait for services
wait
