# Learning Architecture — Claude Code Project Instructions

## What This Is
Claudia Canu Fautré's professional portfolio of educational design frameworks, case studies, and methods — powered by Mission Canvas, a governed agent OS.

## Architecture

This repo has two layers:

### 1. Portfolio Layer (Claudia's education work)
- `case-studies/` — 3 case studies with maturity labels
- `methods/` — 2 validated methods (AI workflow, assessment)
- `resume-cv/` — Professional CV
- `publication-policy.md` — Privacy and transparency rules

### 2. Engine Layer (Mission Canvas)
- `src/` — Python runtime (governed pipeline, gateway, integrity)
- `ontology/` — 137-node classification system
- `knowledge/` — Evidence-tiered library (148 entries, 526 citations)
- `lenses/` — Interpretive filters + Claudia's person lens + Malaguzzi voice guide
- `memory/` — Path-structured persistence (Redis + NDJSON)
- `agents/` — 6 intent agents + orchestrator
- `skills/` — Education skills + morphable capability layer
- `config/` — Three-tier governance
- `runtime/` — Node.js message broker + voice hub
- `tests/` — Gateway, ontology, memory, knowledge, integration

## Palette Connection

This repo is governed by Palette methodology from `~/pretendhome/palette/`. All substantive changes should follow the Palette skill execution cadence.

### Before Making Changes

1. **Pull latest from both repos**:
   ```bash
   cd ~/learning-architecture && git pull origin main
   cd ~/pretendhome && git pull origin main
   ```

2. **Load the relevant Palette skill**:
   - For content/case studies: `~/pretendhome/palette/skills/education/`
   - For resume/CV updates: `~/pretendhome/palette/skills/talent/`
   - For Claudia's full profile: `~/pretendhome/palette/skills/talent/claudia-canu-fautre-profile.md`

3. **Check the publication policy** (`publication-policy.md`) before adding content:
   - No institution names (use "a 4-campus IB international school")
   - No student names or individual data
   - No colleague names
   - No proprietary school documents
   - Every artifact must have a maturity label

4. **Use Palette's evidence bar**:
   - Claims must be traceable to evidence
   - Numbers must be real and defensible
   - Maturity labels must be honest

### Commit Convention
```
<type>(<scope>): <description>

Types: feat, fix, docs, refactor
Scopes: case-study, method, resume, engine, lens, skill, meta
```

## Key Rules

1. **Privacy first.** Never commit identifiable student data, institution names, or colleague names.
2. **Honest maturity labels.** Every framework/method gets a label. Don't inflate.
3. **Palette source of truth.** Claudia's profile lives in Palette. This repo is the public-facing portfolio.
4. **Evidence-based claims only.** If you cite a number, it must be real and defensible.
5. **Glass-box.** Every design decision should be traceable. No black boxes.
6. **Engine integrity.** Don't modify `config/core.md` without explicit human approval (Tier 1, immutable).

## Running Tests
```bash
pip install -e .
pytest -q tests/
```

## Do NOT
- Commit personally identifiable information about children
- Name the school (use generic description)
- Present proposed work as validated
- Modify Tier 1 governance rules without human approval
- Push without checking publication policy
