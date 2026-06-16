# Install Script Readiness — Gap Analysis

**Date**: 2026-06-04  
**Status**: Assessment only

---

## What We Already Have (Palette's setup.sh + install.sh)

The existing `install.sh` (29 lines) + `setup.sh` (420 lines) is already 90% of what Hermes does:

| Feature | Hermes | Us (Palette) | Status |
|---------|--------|-------------|--------|
| One-curl install | ✅ `curl ... \| bash` | ✅ `curl -fsSL .../install.sh \| bash` | DONE |
| Branded banner | ✅ Purple box | ✅ Box with "Mission Canvas" | DONE |
| OS detection | ✅ "Detected: linux (ubuntu)" | ✅ `$(uname -s)` detection | DONE |
| Python check/install | ✅ via uv | ✅ via apt/brew, offers to install | DONE |
| Node.js check/install | ✅ check only | ✅ check + offer install via nodesource | DONE |
| Git check | ✅ | ✅ implicit (clone fails without it) | DONE |
| Internet check | ✅ explicit | ❌ not checked | GAP |
| Ollama install | ❌ (uses external APIs) | ✅ offers to install + pull model | WE WIN |
| uv detection | ✅ required | ✅ optional (faster if present) | DONE |
| venv creation | ✅ explicit | ✅ via uv/pip | DONE |
| Build tools (sudo) | ✅ asks permission | ❌ doesn't ask | MINOR GAP |
| Ripgrep | ✅ checks | ❌ not needed | N/A |
| ffmpeg | ✅ for TTS | ❌ not needed yet | N/A |
| Browser engine | ✅ Playwright/Chromium | ❌ not yet (Sprint 3) | PLANNED |
| Skills sync | ✅ 90 skills | ❌ skills are YAML, already in repo | DIFFERENT |
| API key wizard | ✅ interactive | ✅ interactive (5 providers) | DONE |
| LiteLLM config gen | ❌ | ✅ auto-generates from collected keys | WE WIN |
| Start services | ❌ separate command | ✅ starts broker + hub + LiteLLM | WE WIN |
| Open browser | ❌ | ✅ auto-opens localhost:7890 | WE WIN |
| PATH setup | ✅ adds to shell | ✅ symlinks to ~/.local/bin | DONE |
| Competitor import | ✅ OpenClaw detection | ❌ | GAP (not priority) |
| Non-interactive mode | ❌ | ✅ `--skip-keys` flag | WE WIN |
| Health check at end | ❌ | ❌ (runs tests but not `mc health`) | SMALL GAP |
| Completion message | ✅ | ✅ shows all URLs + commands | DONE |

---

## What Needs to Change for the New Repo

The scripts are solid. The changes are:

### 1. `install.sh` — Update clone URL

```bash
# OLD (points to palette)
git clone --quiet https://github.com/pretendhome/palette.git "$INSTALL_DIR"

# NEW (points to mission-canvas)
git clone --quiet https://github.com/pretendhome/mission-canvas.git "$INSTALL_DIR"
```

Also update `INSTALL_DIR` default:
```bash
# OLD
INSTALL_DIR="${MISSION_CANVAS_DIR:-$HOME/.mission-canvas}"

# NEW (same — this is already correct!)
INSTALL_DIR="${MISSION_CANVAS_DIR:-$HOME/.mission-canvas}"
```

### 2. `setup.sh` — Update paths

The setup.sh currently references Palette-specific paths:
- `$SCRIPT_DIR/peers/` → becomes `$SCRIPT_DIR/runtime/` (new structure)
- `$SCRIPT_DIR/peers/hub/` → becomes `$SCRIPT_DIR/runtime/hub/`
- `$SCRIPT_DIR/peers/broker/` → becomes `$SCRIPT_DIR/runtime/broker/`
- `$SCRIPT_DIR/scripts/palette_intents/palette` → becomes `$SCRIPT_DIR/mc`
- `palette` command → `mc` command
- `.palette/` workspace dirs → keep or rename to `.mc/`

### 3. `setup.sh` — Add missing checks

```bash
# Internet connectivity (Hermes does this)
echo -e "→ Checking internet connectivity..."
if curl -s --max-time 5 https://raw.githubusercontent.com/pretendhome/mission-canvas/main/README.md >/dev/null 2>&1; then
    ok "Internet connectivity"
else
    warn "No internet — external research and model APIs will not work"
fi
```

### 4. `setup.sh` — Add `mc health` at end

```bash
# After services start, run health check
echo ""
echo -e "${BOLD}Running health check...${NC}"
python3 src/mc_cli.py health 2>/dev/null && ok "System healthy" || warn "Some checks failed — run 'mc health' for details"
```

### 5. `setup.sh` — Install Python deps from pyproject.toml

```bash
# OLD: manual package list
$PIP_CMD -q httpx pyyaml ruamel.yaml numpy anthropic

# NEW: install from project
$PIP_CMD -q -e "." 2>/dev/null || pip install pyyaml redis 2>/dev/null
```

---

## Testing the Install Flow

**How to test without pushing to GitHub:**

```bash
# Simulate the curl | bash flow locally
cd /tmp
rm -rf test-mc-install
MISSION_CANVAS_DIR=/tmp/test-mc-install bash ./install.sh
```

This will clone from GitHub (will fail until repo exists), but tests the setup.sh flow with a real directory.

**How to test setup.sh standalone (no clone needed):**

```bash
cd mission-canvas
bash setup.sh --skip-keys
```

This runs the full dependency check + install + service start without requiring API keys.

**How to test the missioncanvas.ai redirect:**

The `curl -fsSL https://missioncanvas.ai/install.sh | bash` URL needs:
- A DNS record for `missioncanvas.ai`
- A web server (or GitHub Pages redirect) that serves the install.sh
- OR simply redirect to `https://raw.githubusercontent.com/pretendhome/mission-canvas/main/install.sh`

**Simplest approach**: Have `missioncanvas.ai/install.sh` be a 301 redirect to the GitHub raw URL. Then the actual script lives in the repo and is always current.

---

## The Final Install Experience (What Users See)

```
$ curl -fsSL https://missioncanvas.ai/install.sh | bash

┌──────────────────────────────────────────┐
│  Mission Canvas Installer                │
│  The governed agent OS for professionals  │
└──────────────────────────────────────────┘

  → Cloning Mission Canvas...
  ✓ Cloned to /home/user/.mission-canvas

┌──────────────────────────────────────────┐
│  Mission Canvas                          │
│  The governed agent OS for professionals  │
└──────────────────────────────────────────┘

Detected: linux (x86_64)

Checking dependencies...
  ✓ Python 3.12
  ✓ Node.js 22.22.2
  ✓ npm 10.9.0
  ? Ollama not found — install for fully local AI? (recommended)
    Install Ollama? [Y/n]: y
  ✓ Ollama installed
  ✓ Local model ready (qwen2.5:3b)
  ✓ uv 0.10.6
  → Checking internet connectivity...
  ✓ Internet connectivity

Installing Python packages...
  ✓ Core packages

Installing Node packages...
  ✓ Peers bus
  ✓ Voice Hub

API Keys (all optional — press Enter to skip)

  Perplexity API key (for external research): pplx-xxxxx
  ✓ Perplexity key set
  Rime API key (for voice/TTS — optional): 
  Skipped — text-only mode
  ...
  ✓ Keys written
  ✓ LiteLLM config generated (3 models)

Starting Mission Canvas...
  ✓ Peers bus (port 7899)
  ✓ Voice Hub (port 7890)
  ✓ LiteLLM router (port 4000)

Running health check...
  ✓ System healthy (94%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mission Canvas is running.

  Open:  http://localhost:7890

  Voice Hub:    http://localhost:7890
  Peers Bus:    http://localhost:7899
  LiteLLM:      http://localhost:4000

  CLI:          mc research "your question"
  Intents:      mc protect | research | decide | create | diagnose | reflect
  Health:       mc health

  Stop:         pkill -f 'node.*server.mjs'; pkill -f 'node.*index.mjs'

Your judgment compounds here.
```

---

## Action Items Before Push

1. [ ] Copy `install.sh` from Palette → MC, update clone URL
2. [ ] Copy `setup.sh` from Palette → MC, update paths (peers/ → runtime/)
3. [ ] Add internet connectivity check
4. [ ] Add `mc health` at end of setup
5. [ ] Change `palette` command references to `mc`
6. [ ] Install Python deps from pyproject.toml not manual list
7. [ ] Test: `bash setup.sh --skip-keys` from the MC directory
8. [ ] Set up missioncanvas.ai/install.sh redirect to GitHub raw URL

---

**The install flow is 90% done from Palette's work. The changes are path updates and polish, not new architecture.**
