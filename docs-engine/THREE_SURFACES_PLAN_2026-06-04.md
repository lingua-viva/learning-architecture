# Three Surfaces Plan — missioncanvas.ai + CLI + Localhost

**Date**: 2026-06-04  
**Goal**: Three experiences, one system, seamless transitions between them

---

## The Three Surfaces

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│   SURFACE 1: missioncanvas.ai (public site)                      │
│   "See what it does. Try the install command."                    │
│                                                                   │
│         ↓ curl -fsSL https://missioncanvas.ai/install.sh | bash  │
│                                                                   │
│   SURFACE 2: CLI (mc command)                                    │
│   "Use it from your terminal. Fast, governed, composable."       │
│                                                                   │
│         ↓ mc open (or auto-opens after setup)                    │
│                                                                   │
│   SURFACE 3: localhost:7890 (local web app)                      │
│   "Full visual interface. Same pipeline. All local."             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Surface 1: missioncanvas.ai

### Current State
- ✅ Live on GitHub Pages (from palette repo)
- ✅ Custom domain with HTTPS
- ✅ install.sh served at `/install.sh`
- ✅ Same HTML as the local app (intent chips, governance signals, voice input)
- ✅ Detects localhost vs public and routes accordingly
- ⚠️ Public mode routes to VPS (`srv1390882.hstgr.cloud`) — may or may not be running
- ⚠️ GitHub links point to `pretendhome/palette`
- ⚠️ Stats show old numbers (131 nodes, 203 KL)

### What It Should Do
The public site is a **showcase + onboarding portal**. When someone visits without having installed:

1. **Hero**: Logo, tagline, input (greyed out with tooltip: "Install locally to use — your data never leaves your machine")
2. **Intent chips visible** but clicking them shows a modal: "Mission Canvas runs on YOUR machine. Install in 60 seconds:"
3. **Install section prominent**: The curl command, one click to copy
4. **After-install section**: "Once installed, your local server runs at localhost:7890 — this same interface, but fully governed and private."
5. **CLI examples section**: Show `mc research "..."`, `mc protect "..."` etc with sample outputs

### Changes Needed
```
1. Disable the chat input on the public site (or show a demo response explaining governance)
2. Add a "Post-Install" section showing what the CLI looks like
3. Add a "What happens when you install" section:
   - Shows the terminal output (branded, with checkmarks)
   - Shows the browser opening
   - Shows a sample governed query flowing
4. Update GitHub links → pretendhome/mission-canvas
5. Update stats → 137 nodes, 148 entries, 65 tests
6. install.sh clone URL → pretendhome/mission-canvas
```

### Where It's Served From (After Migration)
Option A: Serve from `mission-canvas` repo's `docs/` directory via GitHub Pages  
Option B: Keep a separate `gh-pages` branch with just the static site  

**Recommendation**: Option A — serve from `docs/public/` in the mission-canvas repo. The `index.html` for the public site is a modified version of `runtime/hub/index.html` with:
- Chat input disabled (or showing a demo)
- Install CTA prominent
- After-install guide section added

---

## Surface 2: CLI (`mc` command)

### Current State
- ✅ `mc research "..."`, `mc protect "..."` etc all work
- ✅ `mc health`, `mc stats`, `mc candidates`
- ✅ Shows classification, confidence, steps, duration
- ⚠️ No `mc open` command to launch the local web app
- ⚠️ No post-install welcome message that teaches the CLI

### What It Should Do After Install

The LAST thing `setup.sh` prints:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Mission Canvas is running.

  ┌─────────────────────────────────────────────────┐
  │  Web:    http://localhost:7890                   │
  │  CLI:    mc research "your question"            │
  │  Health: mc health                              │
  │  Stop:   mc stop                                │
  └─────────────────────────────────────────────────┘

  Quick start:
    mc research "What are Delaware fiduciary duty standards?"
    mc protect "My client's strategy involves..."
    mc decide "Should we settle or litigate?"

  Your judgment compounds with every query.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### New Commands Needed
- `mc open` — starts services if not running, opens localhost:7890
- `mc stop` — kills broker + hub + api_server
- `mc status` — shows which services are running (ports, PIDs)

---

## Surface 3: localhost:7890 (Local Web App)

### Current State
- ✅ Full HTML/CSS/JS app with intent chips, voice, governance signals
- ✅ SSE streaming from hub server
- ✅ Markdown rendering, citations
- ⚠️ Currently routes to model APIs directly (Claude is fixing this)
- ⚠️ When pipeline API is wired, this becomes the full governed experience

### What It Should Do
After `curl | bash` and browser opens:

1. **First-run experience**: A single-use welcome card appears:
   ```
   ✓ Mission Canvas is running locally.
   
   Everything stays on this machine unless you explicitly research externally.
   Try: "What are the fiduciary duty standards in Delaware?"
   
   [Dismiss]
   ```

2. **Every query shows governance signals in real-time**:
   ```
   🛡️ SCAN: No PII detected
   🏷️ CLASSIFY → RIU-709 Fiduciary Duty Analysis (80%)
   📚 RETRIEVE → 3 knowledge entries (tier 1-2)
   🔒 RESEARCH → BLOCKED (node is privileged)
   🧠 REASON → LOCAL (ollama/qwen2.5:3b)
   💾 STORED → path record #47
   ```

3. **Footer shows system health**: "137 nodes • 148 entries • 47 paths • Q2S: 4"

4. **The intent chips ARE the CLI intents**: clicking PROTECT is `mc protect`, clicking RESEARCH is `mc research`. Same pipeline, same governance.

---

## The Seamless Flow (User Journey)

```
1. Lands on missioncanvas.ai
   → Sees: professional, clean, intent chips, governance promise
   → Sees: "curl -fsSL https://missioncanvas.ai/install.sh | bash"
   → Copies command

2. Runs curl in terminal
   → Branded installer with checkmarks
   → Auto-detects OS, installs deps
   → Prompts for API keys (all optional)
   → Starts services
   → Browser auto-opens localhost:7890
   → Terminal shows: "mc research 'your question'" examples

3. Browser shows localhost:7890
   → Same beautiful UI they saw on the public site
   → But now the input WORKS
   → Types: "What are Delaware fiduciary duty standards?"
   → Real-time governance signals appear
   → Cited, governed response streams in
   → Everything stayed local

4. Later, uses CLI
   → mc research "breach of fiduciary duty California"
   → Same pipeline, same governance, terminal output
   → mc health → system integrity
   → mc stats → sees path records compounding
```

---

## Implementation Handoff to Claude

### Priority 1 (Blocks demo): API server wiring
Already sent via bus. `src/api_server.py` + `server.mjs` update.

### Priority 2: Public site updates
```
Files: runtime/hub/index.html (serves both public and local)
Changes:
- When on public site (not localhost): show "Install to use" CTA instead of functional input
- OR: let input work but show a DEMO response explaining what would happen locally
- Update stats, links
- Add "After Install" section with CLI examples and localhost screenshot
```

### Priority 3: CLI additions
```
Files: src/mc_cli.py
Add:
- mc open: starts services + opens browser
- mc stop: kills services
- mc status: shows running services
```

### Priority 4: setup.sh updates
```
- Start api_server.py on port 7891
- Show the clean completion message with web + CLI instructions
- Auto-open browser to localhost:7890
```

### Priority 5: GitHub Pages migration
```
After mission-canvas repo is pushed:
- Enable GitHub Pages from docs/public/ (or root)
- CNAME: missioncanvas.ai
- DNS: point to GitHub Pages IPs
- The install.sh at missioncanvas.ai/install.sh now clones mission-canvas (not palette)
```

---

## The Key Insight

**The public site and the local app are the SAME HTML.** The only difference is:
- Public: `HUB = 'https://srv1390882.hstgr.cloud'` (demo/showcase mode)
- Local: `HUB = 'http://localhost:7890'` (full governed mode)

The JS already detects this (`location.hostname === 'localhost'`). So the migration is:
1. Push `index.html` to the new repo's Pages directory
2. Point CNAME
3. The same file serves both uses

**The three surfaces are one codebase.** CLI calls the pipeline directly. Web calls the pipeline via API server. Public site shows what it looks like. All governed by the same ontology, same gates, same memory.
