# SPEC: Desktop Package — Ship ontology.engine's Full Dependency Closure (LV-DESKTOP-ONTOLOGY)

**Date**: 2026-07-22
**Status**: SHIPPED — built and live-verified this session
**Author**: Claude (this session)
**Trigger**: Reconciling `SPEC_LV_MULTI_LANE_MERGE_STRATEGY_2026-07-22.md`'s note that
"`ontology/engine.py` now exists in-repo, so Ask's original 'always errors' premise
no longer holds" against this session's own earlier, directly-reproduced
`ModuleNotFoundError: No module named 'ontology.engine'` from the actual installed
desktop app. Both were true — they were describing two different runtime contexts.
**Scope**: `desktop/package.json`'s `extraResources.filter` only. No application code
changed.
**Risk level**: LOW-MEDIUM — the LOW part is packaging config; the MEDIUM part is
that getting this wrong in the ship-too-much direction leaks a real person's private
data (see §3) to every install.

---

## 1. The reconciliation

`ontology/engine.py` has existed in this repo's git history since 2026-06-16 —
over a month before today. The source tree (what a dev server run against the git
checkout uses) has always had it. **The packaged desktop `.exe` never did** —
`desktop/package.json`'s `extraResources.filter` only ever listed
`"ontology/education/**"`, never `ontology/engine.py` itself or any of its real
dependencies. So:

- Any lane testing against a source-tree dev server (not the packaged app) correctly
  found the import working — SPEC_LV_UI_WIRING_FIXES's caveat about this is accurate
  for that context.
- This session's own earlier direct test against the actually-installed
  `LinguaViva-Setup.exe` correctly found it broken — also accurate, for that context.

Neither finding was wrong. The packaging gap was real and, until this spec, still
unfixed.

## 2. Full dependency closure — traced by hand, not guessed

`src/pipeline.py`'s top-level imports (the actual entry point both Ask's
`/api/query` and `ObservationCapturePipeline` depend on transitively) are:

```python
from ontology.engine import OntologyEngine, ClassificationResult
from memory.store import MemoryStore
from memory.schema import PathRecord
from knowledge import KnowledgeStore
from src.context_builder import ContextBuilder   # already covered by src/**
from lenses import LensEngine
from ontology.proposals.candidate import CandidateStore
from ontology.learned_weights import LearnedWeights
```

Each was traced to its own imports in turn (not assumed):

| Import | What it actually needs |
|---|---|
| `ontology.engine` | `ontology/__init__.py`, `ontology/engine.py`, `ontology/schema.yaml`, `ontology/core/**`, `ontology/domains/**` (loads via `Path(__file__).parent`-relative globs — verified no `graph.py`/`integrity/` dependency despite docstring mentions, those are prose only) |
| `memory.store` (pulled in eagerly by `memory/__init__.py` regardless of which submodule is actually wanted) | the full `memory/` package — `store.py`, `schema/`, `compaction.py`, `handoff.py`, `notes.py`, `redis_adapter.py`, `ndjson_adapter.py` (all stdlib-only despite the name, no real `redis` dependency) |
| `knowledge` | `knowledge/__init__.py`, top-level `knowledge/*.yaml`, `knowledge/education/**` — confirmed via `KnowledgeStore._load()` that `knowledge/proposals/` is never scanned, so it's correctly omitted |
| `lenses` | `lenses/__init__.py`, `lenses/engine.py`, and — confirmed via `LensEngine._load_lenses()` — **only** `lenses/core/**`, `lenses/professional/**`, `lenses/education/**` (see §3 for why the two top-level loose files are deliberately excluded) |
| `ontology.proposals.candidate` | `ontology/proposals/**` |
| `ontology.learned_weights` | `ontology/learned_weights.py` (the `.yaml` data file is deliberately excluded — see §4) |

## 3. Privacy exclusion — read this before ever changing the filter to `lenses/**`

`lenses/` has two loose top-level files alongside its `core/`/`professional/`/
`education/` subdirectories: `LENS-PERSON-002_claudia_canu.yaml` and
`VOICE-EDU-001_malaguzzi_inspired.md`. The first is **a real person's private
profile** — Claudia Canu Fautré's career history, roles, and (per its own header)
sources including "family finance analysis." `LensEngine._load_lenses()`
(`lenses/engine.py`) only ever globs `core/`, `professional/`, and `education/` —
it never reads either loose top-level file. **There is no functional reason to ship
either one, and a strong reason not to**: doing so would put a real, named
individual's private profile on every teacher's machine who downloads the app.
`tests/test_desktop_ontology_packaging.py::test_personal_lens_file_is_never_shipped`
locks this in — it explicitly fails if the filter ever becomes a blanket
`"lenses/**"`.

## 4. Accumulated dev-machine state — also excluded, also verified safe to exclude

`ontology/learned_weights.yaml` and `memory/data/paths.ndjson` are both
auto-accumulated from real query traffic on **this specific development machine** —
not code, not fixtures, just history. Shipping them would seed every fresh install
with this dev machine's session data instead of a clean slate. Confirmed safe to
omit: `LearnedWeights._load()` checks `self._path.exists()` and starts with an empty
`{}` if absent — no crash, no missing-file error, just a cold start (exactly what a
fresh install should have).

## 5. Live verification (not just filter-list reasoning)

Static analysis of what a filter *should* include is necessary but not sufficient —
verified end to end against the actually-installed app, same technique used earlier
this session for the Doctor desktop-mode fix:

1. Mirrored every newly-required path (per §2/§3/§4's final list) into
   `C:\Users\...\Programs\lingua-viva-desktop\resources\app\`.
2. Direct Python import check from that directory: `from ontology.engine import
   OntologyEngine` — succeeded, 111 nodes loaded, `classify()` returned a real
   result.
3. Restarted the actual running desktop server process (`LV_DESKTOP=1`), confirmed
   `/api/health` still `OK`.
4. **The real test**: `POST /api/query` with `"how do i add a lens"` — previously
   returned `{"error": "No module named 'ontology.engine'"}` rendered as a fake
   answer (the bug `SPEC_LV_UI_WIRING_FIXES` made honest-looking rather than fixing
   the root cause, correctly, per its own stated scope). **Now returns a real,
   complete pipeline result** — `SCAN→CLASSIFY→RETRIEVE→REASON→SYNTHESIZE→STORE`,
   `external_called: false`, real local model content from `ollama/qwen2.5:3b`.
5. Confirmed `ObservationCapturePipeline` (the other consumer of `ontology.engine`,
   currently unused by any live route but needed for a future Spec 6) now also
   imports cleanly from the installed app's directory.

The classification landed on a mediocre node match (`LV-LRN-001` / "Self-Assessment
Prompt", confidence 0.6, for a question about adding a lens) — that's the ontology
classifier's own retrieval-quality question, explicitly deferred by the operator to
a session ~2 weeks out (same deferral as Ask's original bug report). Not this spec's
concern: this spec's job was "does the pipeline run at all in the packaged app,"
and it now does.

## 6. What Does NOT Change

- No application code — `ontology/engine.py`, `src/pipeline.py`,
  `observation_capture.py` etc. are all untouched.
- The classifier's retrieval quality/accuracy — untouched, out of scope, deferred.
- `doctor/support_loop/doctor.py`'s desktop-mode fix — untouched (separate fix,
  separate commit).

## 7. Definition of Done

- [x] Full dependency closure traced by reading actual import statements, not
      assumed from directory names
- [x] Personal-data exclusion (`LENS-PERSON-002_claudia_canu.yaml`,
      `VOICE-EDU-001_malaguzzi_inspired.md`) verified both necessary (real
      private profile) and safe (never read by the actual import chain)
- [x] Accumulated dev-machine state (`learned_weights.yaml`, `memory/data/`)
      excluded, verified safe via the consuming classes' own missing-file handling
- [x] Live-verified against the actually-installed desktop app: `/api/query` runs
      the complete pipeline, real model response, zero external calls
- [x] `ObservationCapturePipeline` (Spec 6's future dependency) also confirmed
      importable from the installed app
- [x] Regression tests added (`tests/test_desktop_ontology_packaging.py`, 3 tests)
      locking in both the dependency closure and the two privacy exclusions
- [x] `python3 -m pytest -q` on directly-relevant test files: all pass, no
      regressions

## 8. Provenance

Traced by reading, in full: `ontology/engine.py`, `src/pipeline.py`'s complete
import block, `memory/__init__.py` + `memory/store.py`, `lenses/engine.py`
(specifically `_load_lenses()`), `knowledge/__init__.py` (specifically `_load()`),
`ontology/learned_weights.py` (specifically `_load()`'s missing-file tolerance).
Live-verified against `C:\Users\spide\AppData\Local\Programs\lingua-viva-desktop\
resources\app` by direct file mirroring, process restart, and a real
`/api/query` call — not inferred from the filter list alone.
