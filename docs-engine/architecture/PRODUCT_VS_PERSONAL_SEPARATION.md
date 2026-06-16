# Mission Canvas — Separation of Concerns: Product vs Personal

**Date**: 2026-06-12
**Author**: kiro.design
**Status**: Brainstorm → Guiding Principle
**Problem**: MC must be pristine for any new user. Mical also needs a personalized MC for dogfooding. These cannot be the same thing.

---

## The Problem Stated Clearly

We have three repos:
- `pretendhome/pretendhome` (private) — monorepo sandbox, everything lives here during development
- `pretendhome/palette` (public) — intelligence layer, on job applications, stays for now
- `pretendhome/mission-canvas` (public) — the PRODUCT. Must be zero-state clean at all times.

**Constraint 1**: Anyone who clones `mission-canvas` must get a clean, impersonal, ready-to-use system. No traces of Mical, no personal data, no dogfooding artifacts.

**Constraint 2**: Mical needs a PERSONAL instance of MC that adapts to him — path records, preferences, personal knowledge, dogfooding data. This is where MC proves itself.

**Constraint 3**: Improvements discovered during dogfooding must flow BACK to the clean product without carrying personal data.

---

## The Guiding Principle

**The product is the engine. The user is the fuel. They never mix in the repo.**

Or more precisely:

> **Mission Canvas ships as a stateless runtime. All personalization lives in a user-owned data directory that the product never commits, never ships, and never assumes exists.**

This is the same pattern as:
- **VS Code**: Product installs to `/usr/lib/`. User settings/extensions live in `~/.config/Code/`.
- **Obsidian**: App is generic. Vault (user data) is a separate folder the user controls.
- **Neovim**: Binary ships clean. Config lives in `~/.config/nvim/`. Plugins in `~/.local/share/nvim/`.
- **Oh-my-zsh**: Framework in `~/.oh-my-zsh/`. User config in `~/.zshrc`. Custom plugins in `custom/` (gitignored).
- **Hugo**: Engine is generic. User content is a separate project that USES Hugo.
- **Home Assistant**: Core is generic. User config in `/config/` which is their own directory.

---

## The Architecture

```
pretendhome/mission-canvas (PUBLIC — the product)
├── src/            ← Pipeline, gates, CLI — generic, stateless
├── ontology/       ← Base ontology nodes — ships with product
├── knowledge/      ← Base knowledge library — ships with product
├── config/         ← Default governance — ships with product
├── lenses/         ← Core lenses — ships with product
├── skills/         ← Core skills — ships with product
├── runtime/        ← Broker, hub — ships with product
├── tests/          ← All tests — ships with product
└── static/         ← Web UI assets — ships with product

~/.mission-canvas/ (USER DATA — never committed, never shipped)
├── config.yaml         ← User overrides (API keys, model prefs)
├── memory/             ← Path records, session history
├── knowledge/          ← User-added knowledge entries
├── ontology/           ← User-added nodes (proposals promoted)
├── lenses/             ← User-created lenses
├── skills/             ← User-created skills
├── sessions/           ← Session state files
└── logs/               ← Runtime logs

pretendhome/pretendhome (PRIVATE — Mical's dogfood instance)
├── .mc/                ← Mical's personal MC data (same structure as ~/.mission-canvas/)
│   ├── memory/
│   ├── knowledge/
│   ├── lenses/
│   └── ...
├── palette/            ← Intelligence layer (subtree → public)
└── mission-canvas/     ← Product (subtree → public)
```

---

## How It Works

### For a New User (clone from zero)

```bash
curl -fsSL https://missioncanvas.ai/install.sh | bash
# Creates ~/.mission-canvas/ with empty user data dirs
# Copies config.example.yaml → ~/.mission-canvas/config.yaml
# Product ontology + knowledge are the ONLY starting knowledge
# First query creates first path record in user's local memory
```

They start with ZERO personal state. The product works generically. Over time, their `~/.mission-canvas/` fills with THEIR path records, THEIR knowledge, THEIR lenses. That's theirs forever. Product updates don't touch it.

### For dogfooding

```bash
# MC_DATA_HOME points to the operator's personal data directory
export MC_DATA_HOME=~/.mc
mc research "What's the hybrid router architecture?"
# Path record saved to ~/.mc/memory/
# Personal knowledge available from ~/.mc/knowledge/
```

The operator's personal state lives outside the product repo. It can be versioned (privately), backed up, or analyzed. It never leaks to the public repos.

### For Product Development

When dogfooding reveals a product improvement:
1. Fix goes to `pretendhome/mission-canvas` (the product code)
2. Subtree push to public `pretendhome/mission-canvas`
3. Mical's personal data (`/fde/.mc/`) is NEVER touched by this flow
4. Mical's data never appears in git diffs of the product

---

## The Environment Variable

```python
# In src/session.py or wherever data paths are resolved:
import os
from pathlib import Path

def get_data_home() -> Path:
    """User data directory. Never inside the product repo."""
    explicit = os.environ.get("MC_DATA_HOME")
    if explicit:
        return Path(explicit)
    # XDG-compliant default
    xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(xdg) / "mission-canvas"

def get_config_home() -> Path:
    """User config directory."""
    explicit = os.environ.get("MC_CONFIG_HOME")
    if explicit:
        return Path(explicit)
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg) / "mission-canvas"
```

Or simpler (matching Obsidian/oh-my-zsh pattern):
```python
MC_HOME = Path(os.environ.get("MC_HOME", os.path.expanduser("~/.mission-canvas")))
```

---

## What Lives Where — Decision Matrix

| Content Type | Product Repo | User Data Dir | Rationale |
|---|---|---|---|
| Pipeline code | ✅ | ❌ | Engine, not fuel |
| Base ontology (137 nodes) | ✅ | ❌ | Ships with product |
| User-added ontology nodes | ❌ | ✅ | Their personalization |
| Base knowledge (148 entries) | ✅ | ❌ | Ships with product |
| User-added knowledge | ❌ | ✅ | Their discoveries |
| Default governance (Tier 1) | ✅ | ❌ | Immutable product rules |
| User config (API keys, prefs) | ❌ | ✅ | Their credentials |
| Path records / memory | ❌ | ✅ | Their judgment history |
| Session state | ❌ | ✅ | Their active work |
| Lenses (core) | ✅ | ❌ | Ships with product |
| Lenses (user-created) | ❌ | ✅ | Their perspectives |
| Skills (core) | ✅ | ❌ | Ships with product |
| Skills (user-created) | ❌ | ✅ | Their automations |
| Tests | ✅ | ❌ | Product quality |
| Golden datasets | ✅ | ❌ | Product measurement |
| Reports / analysis | ❌ | ✅ (or private repo) | Dogfooding artifacts |
| Logs | ❌ | ✅ | Runtime noise |

---

## The Merge Problem: Product Ontology + User Ontology

When MC starts, it needs to load BOTH:
- Base ontology from product (`ontology/domains/`)
- User additions from `~/.mission-canvas/ontology/`

**Resolution order** (same as CSS cascade or Neovim config):
1. Product defaults load first (137 nodes)
2. User additions layer on top (additive — new nodes)
3. User overrides can shadow product nodes (rare, explicit)
4. Tier 1 governance from product is IMMUTABLE — user cannot override

This means the ontology engine does:
```python
def load_ontology():
    base = load_product_ontology()  # from product repo
    user = load_user_ontology()      # from MC_HOME/ontology/
    return merge(base, user)         # user adds, product rules win conflicts
```

---

## What This Means for Current Repos

| Repo | Role Going Forward |
|------|-------------------|
| `pretendhome/pretendhome` (private) | Mical's workspace. Contains `.mc/` with personal MC data. Contains `palette/` and `mission-canvas/` as subtrees for development. |
| `pretendhome/mission-canvas` (public) | THE PRODUCT. Stateless. Clean. Any user starts from zero. Never contains personal data. |
| `pretendhome/palette` (public) | Intelligence layer. Stays for now (job apps reference it). Eventually: palette's knowledge gets absorbed INTO MC's base ontology/knowledge. Palette becomes an upstream source, not a separate product. |

---

## Immediate Actions

1. **Add `MC_HOME` resolution to session startup** — one function, ~10 lines
2. **Create `~/.mission-canvas/` scaffold in install.sh** — `mkdir -p` for the standard dirs
3. **Move memory writes to `MC_HOME`** — path records, sessions, logs go to user dir
4. **Add `MC_HOME` to .gitignore in product repo** — safety net
5. **Move operator's dogfood data to `~/.mc/`** — separate from product
6. **Remove personal reports from mission-canvas repo** — they belong in pretendhome or .mc/

---

## The One-Line Principle

> **The product repo is what you `git clone`. The user directory is what you build by using it. They never cross.**

---

*Brainstorm by kiro.design, 2026-06-12 07:10 PT. Ready for operator review.*
