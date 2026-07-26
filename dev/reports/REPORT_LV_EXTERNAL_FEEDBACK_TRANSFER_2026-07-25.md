# REPORT: External-Feedback Transfer — Track A Decisions (2026-07-25)

Spec: `mission-canvas/dev/SPEC_LINGUA_VIVA_EXTERNAL_FEEDBACK_AND_APP_SYNC_2026-07-25.md` §2.
Executed at HEAD `3dde2a4`. Decisions recorded BEFORE any build, per spec discipline.

Decision lens: Claudia's person lens (`lenses/LENS-PERSON-002_claudia_canu.yaml`) + LV's own
education lenses (differentiation-coach / rti-monitor — the learning-specialist perspective).
The test applied to every item: **"how will this help me help my students"** — teachers open
this tool Monday 2026-07-27; anything that doesn't serve that, or that adds regression risk to
that, defers.

> Note: no "Blaise" lens exists anywhere in this repo, palette, or mission-canvas (verified by
> repo-wide grep). If a learning-specialist person lens is wanted, it needs to be authored —
> flagged as a gap, not silently substituted.

## Corrections to the spec's §1a claims (verified against live code first)

1. **Slack bot tokens and Google Drive OAuth tokens are NOT stored in the plaintext provider
   config.** They are read from environment variables at call time (`LV_SLACK_BOT_TOKEN`,
   `LV_SLACK_SIGNING_SECRET` in `src/lingua_viva/slack_integration.py:51-90`;
   `LV_GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN` in `src/lingua_viva/google_drive_integration.py:135`)
   and never written to disk by LV. The plaintext-with-`0o600` file
   (`src/lingua_viva/config.py:182-188`, wrapped by `src/provider_config.py:93`) holds only LLM
   provider API keys — the same stakes as MC's pre-SWEEP_02 state, **not** higher as the spec
   claimed.
2. **`INJECTION_PATTERNS` / `_detect_injection()` do not exist in `archive/mc-engine/` at all**
   (repo-wide grep: zero matches for "injection" anywhere under `archive/`). They were added to
   MC *after* the `c2a9bf5` fork point (`mission-canvas/src/gates/entry.py:41-62`). The archived
   `test_pipeline_entry_gate.py` tests entry-gate blocking/REFLECT short-circuit, not injection.
   So item 2 is a fresh, LV-scoped build, not an un-archiving.
3. **`CandidateStore.evaluate()` and `.promote()` have zero live call sites** (`grep -rn
   "\.evaluate(\|\.promote(" src/` excluding tests = empty; only `CandidateStore()` is
   instantiated at `src/pipeline.py:496`). Candidates get created/enriched, but nothing
   auto-decides promote-vs-discard in the running app. The gap is pure *visibility*, not silent
   auto-promotion.

## The five decisions

| # | Item | Decision | Reasoning |
|---|---|---|---|
| 1 | Secrets provider (SWEEP_02 mirror) | **DEFER** | Stakes were overstated (see correction 1 — third-party creds are env-var-sourced, not in the file). No user of an external secrets backend exists: the teacher operator will not run bitwarden/keyring config, and the desktop app has no UI for it. Touching the credential save/load path 2 days before first real teacher adoption is regression risk with zero Monday benefit. Revisit after the pilot if/when LV starts persisting third-party tokens itself. |
| 2 | Injection detection | **BUILD NOW** — LV-scoped, high-precision, redact-don't-block | This one passes the teacher test directly: teacher-uploaded documents feed the extraction engine, student lenses, and parent reports. A poisoned or carelessly forwarded document that steers the local model corrupts what the tool tells Claudia about her students — a trust-destroying failure in week one. BUT: MC's pattern list must not be copied blind. K-5 content legitimately contains "You are now a detective!" and "Pretend you are a pirate" — MC's `you\s+are\s+now\s+(a|an|in)` pattern would false-positive on children's material. LV version: only unambiguous injection patterns, applied to ingested document text and queries; matched lines are **redacted and audit-logged, never a silent document rejection** (a teacher on Monday must never lose a document to a false positive with no explanation). Ships with regression tests including an explicit kid-content false-positive guard. |
| 3 | Candidate human-gate | **BUILD (option b, minimal)** — read-only `lv candidates` | Verified no auto-promotion is occurring (correction 3), so option (a) is defensible — but a read-only listing is ~40 lines, zero risk to the app surface (CLI-only), and honors the module's own stated contract ("The system proposes, the human disposes"). Gives the operator visibility into what the ontology thinks it's learning from real teacher usage starting Monday — exactly when candidates will start accumulating for the first time. No promote/confirm machinery (explicit non-goal). |
| 4 | Path-resolution spot check | **DONE (check, not build)** | Findings inline below. |
| 5 | End-to-end smoke runs | **DONE (check, not build)** | Findings inline below. No live Google credentials exist in this environment (`env | grep LV_GOOGLE` = empty), so the Drive run uses the fixture transport — explicitly NOT a real round-trip claim. |

## Item 4 — Path-resolution spot check findings

**PASS — no `_MC_ROOT`-class bug found.** LV does not have MC's fragile
repo-root-relative resolution pattern:

- All runtime state resolves through a single seam: `config_home()` in
  `src/lingua_viva/config.py`, env-overridable via `LV_CONFIG_HOME` (verified by using it
  for the sandboxed Drive smoke run below).
- Filemap normalization (`_normal()`) uses `expanduser().resolve()` — no CWD-sensitive
  relative paths.
- `LV_ROOT = Path(__file__).parent.parent` in `web.py` / `pwa.py` resolves the repo root
  from module location, not from CWD.
- Desktop `appRoot()` = `process.resourcesPath/app` — packaged-app code root is correctly
  split from runtime state (which stays under `~/.lingua-viva/`).

## Item 5 — E2E smoke run findings

### Extraction engine (real run, non-mocked, Ollama qwen2.5:3b live)

| Document | Time | Fields extracted | Chunks |
|---|---|---|---|
| `references/Criteri_Fondanti_Curricolo_Italiano_K-5.pdf` (Italian K-5 curriculum) | 40.9s | 1 (`grade='G1'`, needs_confirmation) | 10 |
| `tests/fixtures/sample_myp_guide.pdf` (English) | 20.1s | 0 | — |

**Mechanical verdict: PASS. Real-world yield: low — recorded as a finding, not rebuilt
(spec non-goal).** Root cause characterized: `_propose_fields` DOES return proposals
(e.g. `{"grade": "G5", "title": "Sample MyP Guide", ...}` — title derived from the
filename), but the literal-grounding invariant correctly rejects paraphrased or
hallucinated values that don't appear verbatim in the source text. The safety invariant
holds exactly as designed; the cost is that a 3B local model rarely quotes literally
enough to survive it. If Monday usage shows teachers getting empty extractions, the fix
direction is prompt-side ("quote exactly"), never a loosening of grounding.

### Drive connector (fixture transport, sandboxed via `LV_CONFIG_HOME=/tmp/lv-smoke-home`)

**PASS** — list → import → disk round-trip:
- Supported file imported with `0600` perms and byte-correct content under
  `/tmp/lv-smoke-home/runtime/drive_imports`.
- PNG correctly rejected as `unsupported_for_import`.
- **Explicitly NOT a real Google round-trip**: no live credentials exist in this
  environment (`env | grep LV_GOOGLE` = empty). A live-cred smoke remains an operator
  task before Monday if real Drive import is expected on day one.

## Build results

### Item 2 — Injection guard (built, tested, green)

- **New:** `src/lingua_viva/injection_guard.py` — 8 unambiguous patterns
  (ignore-previous, disregard-rules, reveal-system-prompt, system-prompt marker,
  `</system>` tag, `[INST]` tag, new-instructions marker, override-rules).
  `REDACTION_TOKEN = "[REDACTED_INJECTION]"`; `detect_injection()` +
  `redact_injection()` returning audit entries `{"layer": "injection_guard", ...}`.
- **Wired into three seams:**
  1. `src/education/document_parser.py::_redact` — injection pass appended after PII
     redaction; matched chunks flag `needs_review`.
  2. `src/lingua_viva/extraction_engine.py::_chunk_plaintext` — covers .txt/.md, which
     bypass DocumentParser.
  3. `src/pipeline.py::GatewayInterface.sanitize_query` — egress seam; blocked
     classifications still return `""`.
- **Redact-and-audit, never reject** — a teacher never loses a document to a false
  positive.
- **Kid-content false-positive guard holds:** "You are now a detective!", "Pretend you
  are a pirate", "Forget everything you knew about fractions", Italian classroom
  language ("Ignora il rumore e concentrati sulla lettura") — none match, by test.
- **Tests:** `tests/test_injection_guard.py` — 34 tests, all green.

### Item 3 — Read-only `lv candidates` (built, tested, green)

- **New CLI subcommand** in `src/lingua_viva/cli.py`: `lv candidates [--all]` — lists
  candidate proposals (ID / STATUS / HITS / DOMAIN / SIGNALS + resolution); hides
  PROMOTED/DISCARDED unless `--all`. Strictly read-only — no evaluate/promote/discard
  machinery (explicit non-goal), verified by a byte-identical before/after test.
- **Live run:** listed 12 real accumulated candidates (e.g. CAND-B6FCE003, 24 hits).
- **Tests:** `tests/test_cli_candidates.py` — 4 tests, all green.
- **Shipping gap (Track B item):** the installed `~/.local/bin/lv` is the compiled
  v1.0.3 release binary — `lv candidates` is built-not-shipped until the next CLI
  release tag. Source invocation works today.

### Regression status

- Pre-change baseline: **704 passed, 13 skipped** (matches spec's expected baseline
  exactly).
- New tests: **38/38 green** (34 injection guard + 4 candidates).
- Full-suite re-run after both tracks: recorded in
  `REPORT_BUILT_TO_SHIPPED_SYNC_2026-07-25.md` per spec §6.
