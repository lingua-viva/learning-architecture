# Production Readiness Circuit — Full Report

**Date**: 2026-07-13
**Scope**: Lingua Viva education fork (`ontology/education/`, `lenses/education/`, `knowledge/education/`)
**Status**: Complete

---

## 1. Corrected Premise

The circuit's original brief assumed the education ontology domain didn't exist yet and needed to be built from scratch. That assumption was false. `ontology/education/` already existed as a designed, 38-node pack (`LV-*` IDs) spanning curriculum, teacher, assessment, student, parent, admin, infrastructure, planning, and learner subdomains. The real problem was that **every one of the 38 nodes was orphaned** — none had a `parent` field — which silently broke the classification engine's depth/ranking logic and the `mc health` check, and (separately) two spec docs (`lenses/education/README.md`, `knowledge/education/README.md`) described lens and knowledge-library content that had never actually been implemented.

This reframed the work from "build a domain" to:
1. Fix the wiring gaps.
2. Implement the two already-designed-but-unbuilt spec docs.
3. Build a real golden query suite and measure baseline routing accuracy.
4. Rehearse the system against realistic demo queries and fix what breaks.
5. Verify the whole repo and document it.

---

## 2. Work Completed

### 2.1 Ontology wiring fix
Added the correct `parent` field to all 38 `LV-*` nodes (`CORE-CREATE`, `CORE-DIAGNOSE`, `CORE-RESEARCH`, `CORE-DECIDE`, or a domain-appropriate `LV-*` parent), matching the convention used by every other domain pack in the repo. This resolved the orphan-node WARN in `mc health`.

### 2.2 Lens engine wiring gap — found and fixed
`LensEngine._load_lenses()` only globbed the top-level `lenses/` directory and never scanned `lenses/education/`. The 9 education lenses specified in the README had never been loadable at runtime. Fixed by extending the loader to also scan the `education` subdirectory. Verified via `tests/test_lenses.py`.

### 2.3 Nine education lens YAML files written
- `curriculum-designer.yaml`
- `differentiation-coach.yaml`
- `rti-monitor.yaml`
- `assessment-specialist.yaml`
- `trauma-informed.yaml`
- `multilingual-learner.yaml`
- `observation-coach.yaml`
- `parent-voice.yaml`
- `school-leader.yaml`

Each follows the existing `lenses/core/protection.yaml` convention: `name`, `description`, `rationale`, `activation` (`on_domain` / `on_signal_keywords`), a single `system_prompt_modifier` block, and `confidence_adjustment: 0.0`. All load and pass `tests/test_lenses.py`.

### 2.4 Knowledge store wiring gap — found and fixed
Same bug class as 2.2: `KnowledgeStore._load()` only globbed `knowledge/*.yaml`, never `knowledge/education/*.yaml`. The 30-entry education knowledge library specified in its README had never been loadable.

```python
# before
def _load(self, knowledge_dir: Path) -> None:
    for yaml_file in sorted(knowledge_dir.glob("*.yaml")):
        ...

# after
def _load(self, knowledge_dir: Path) -> None:
    yaml_files = list(knowledge_dir.glob("*.yaml"))
    for subdir in ["education"]:
        dir_path = knowledge_dir / subdir
        if dir_path.exists():
            yaml_files.extend(dir_path.glob("*.yaml"))
    for yaml_file in sorted(yaml_files):
        ...
```

### 2.5 Thirty education knowledge-library entries written
`LV-KL-001` through `LV-KL-030`, across five files:

| File | Topic |
|---|---|
| `curriculum_ib.yaml` | IB PYP unit design, transdisciplinary themes |
| `differentiation.yaml` | Tiered instruction, scaffolding |
| `rti_assessment.yaml` | RTI tiers, formative/summative assessment |
| `trauma_informed.yaml` | Trauma-informed classroom practice |
| `multilingual_observation.yaml` | L1 transfer, BICS/CALP, observation protocol, grouping |

Each entry has `id`, `title`, `content`, `ontology_nodes` (mapped to real `LV-*` nodes), `evidence_tier` (1 or 2 only — no Tier 3 speculative claims), `citations`, `tags`, `verified: true`. Real sources used: IBO (2018), CEFR Companion Volume (2020), Tomlinson (2014), Fuchs & Fuchs (2006), Cummins (1984), Krashen (1985), SAMHSA (2014), Beck/McKeown/Kucan (2013), García (2009), Wood/Bruner/Ross (1976), Black & Wiliam (1998), VanTassel-Baska (2003), Erickson & Lanning (2014), Hamayan et al. (2013), Danielson (2013), UNHCR (2019), OSEP PBIS TA Center.

**Deliberately excluded**: the source README's "Validated Local Evidence" section, which names a specific real institution — see §4.

### 2.6 Golden query suite built
`tests/golden_education_v1.yaml` — 36 queries:
- 30 covering all 9 education subdomains (curriculum, teacher, assessment, student/PROTECT, parent, admin, infrastructure, planning, learner).
- 6 decoys: 2 cross-domain routes to real `MC-LEGAL-*` nodes, 1 no-signal fallback to `CORE-RESEARCH`, 3 intra-repo ambiguity tests documenting known signal-collision limitations.

The full governed pipeline (`mc eval`, which runs an LLM reasoning pass per query) could not complete in-session: the host was under heavy load (load average 18.26 on 16 cores) from unrelated `llama-server` processes competing for the same local Ollama instance the pipeline calls. Confirmed via `ss -tnp` that the eval process was alive and blocked on `127.0.0.1:11434`, not crashed.

**Workaround**: measured the same routing-accuracy metric directly via `OntologyEngine.classify()`, which bypasses the LLM synthesis steps that don't affect node routing.

**Result: 33/36 (91.7%)**. The 3 misses are a real, root-caused engine limitation, not suite bugs — the signal matcher has no stemming/pluralization and does bag-of-words token-overlap rather than phrase matching, so short generic signals shared across nodes (e.g. "what level") occasionally outrank the semantically correct node.

### 2.7 Demo rehearsal
Ran 6 realistic single-turn teacher-day queries through the real classifier. 3 misrouted on the first pass.

Fixed 2 with targeted, evidence-grounded signal additions:
- **`LV-PAR-002`** (parent-facing progress summary) was missing third-person teacher-relayed phrasing ("how their child is doing," "asked me how," "tell the parent") — only first-person parent phrasing was covered. Added.
- **`LV-PLN-001`** (weekly planning) was missing "tomorrow" / "plan for tomorrow" — only "this week"/"next week"/"Monday" were covered. Added.

Left 1 unfixed and documented rather than band-aided:
- A differentiation query intended for `LV-CUR-002` kept losing the ranking race to `LV-LRN-001` even after adding a matching signal, because `_rank_score()`'s coverage formula (`matched signals ÷ total node signals`) structurally disadvantages nodes with larger signal vocabularies — `LV-CUR-002` (13 signals) scored lower than `LV-LRN-001` (6 signals) for the same 1-signal match. A proper fix means changing the ranking formula or `LV-LRN-001`'s overly generic signal, both engine-wide changes affecting every domain in the repo — out of scope for an education-vertical circuit and unsafe without a full regression pass.

**Final: 5/6.**

---

## 3. Verification

| Check | Result |
|---|---|
| `pytest tests/ -q` (full suite) | 223/223 passed — confirmed across 4 separate runs (including background stragglers), zero regressions |
| `mc health` | 98% (82/84), up from 96% (81/84) at circuit start |
| `KnowledgeStore` entries | 178 total (148 prior + 30 new), 30 correctly attributed to `education` domain |
| Golden routing baseline | 33/36 (91.7%) via direct `OntologyEngine.classify()` |
| Demo rehearsal | 5/6 after fixes |
| `BUILD_JOURNAL.md` | Turn 14 entry appended documenting all of the above |

One earlier background full-pipeline `mc eval` run also completed independently and matched: `214 passed in 186.37s` (a subset run against an older test count at the time) and `Health: 98% (82/84)` — consistent with the figures above.

---

## 4. Flagged, Not Fixed (needs operator decision)

1. **Institution name leak** — `knowledge/education/README.md` and `ontology/education/curriculum.yaml` (header comment line 3, `LV-CUR-001` description line 18) both name a specific real institution ("La Scuola International"). This is a live violation of `publication-policy.md`'s no-institution-names rule. Left in place because redacting shipped ontology/knowledge data across multiple files is a content decision, not a wiring fix, and shouldn't be done unilaterally.
2. **No canvas system** — confirmed by search that no canvas system exists anywhere in this repo. Canvases are a Mission Canvas / Palette concept and not part of this fork; noted in case any future prompt assumes otherwise.
3. **Golden-dataset path-naming inconsistency (pre-existing, not introduced this session)** — three different, non-matching conventions exist:
   - `src/mc_cli.py`'s `run_eval()` defaults to `tests/golden_mc_v1.yaml` (doesn't exist)
   - `src/integrity/health_check.py`'s `_check_test_suite()` looks for `tests/golden_dataset_v1.yaml` (doesn't exist)
   - `_check_golden_accuracy()` looks for `tests/results/golden_results_*.json` (never written by `run_eval()`)

   None of the three match this session's `tests/golden_education_v1.yaml`. This is why `mc health`'s remaining 2/84 WARNs persist even after this circuit's fixes.

---

## 5. Recommended Next Steps

1. **Operator decision** on La Scuola redaction across the two flagged files (§4.1).
2. **Engine-wide follow-up circuit** on ontology signal-matching precision: add stemming/lemmatization, move from bag-of-words token-overlap toward phrase-adjacency matching, and rework `_rank_score()`'s coverage formula so it doesn't structurally penalize nodes with larger signal vocabularies. This is a core-engine change affecting every domain, not education-specific — needs its own scoped circuit and full regression pass.
3. **Reconcile the three golden-dataset path conventions** (§4.3) so `mc eval` and `mc health` agree on a single canonical file, and wire `run_eval()` to actually write `tests/results/golden_results_*.json` so the health check's golden-accuracy section can pass organically instead of always WARNing.

---

## 6. Files Touched This Circuit

**New files:**
- `lenses/education/curriculum-designer.yaml`
- `lenses/education/differentiation-coach.yaml`
- `lenses/education/rti-monitor.yaml`
- `lenses/education/assessment-specialist.yaml`
- `lenses/education/trauma-informed.yaml`
- `lenses/education/multilingual-learner.yaml`
- `lenses/education/observation-coach.yaml`
- `lenses/education/parent-voice.yaml`
- `lenses/education/school-leader.yaml`
- `knowledge/education/curriculum_ib.yaml`
- `knowledge/education/differentiation.yaml`
- `knowledge/education/rti_assessment.yaml`
- `knowledge/education/trauma_informed.yaml`
- `knowledge/education/multilingual_observation.yaml`
- `tests/golden_education_v1.yaml`
- `PRODUCTION_READINESS_REPORT.md` (this file)

**Edited files:**
- `ontology/education/*.yaml` (all files in this directory — added `parent` field to 38 nodes; also added signals to `LV-CUR-002`, `LV-PAR-002`, `LV-PLN-001`)
- `knowledge/__init__.py` (subdirectory-loading fix)
- `lenses/engine.py` (subdirectory-loading fix, done just prior to this circuit segment)
- `case-studies/04-still-i-rise/BUILD_JOURNAL.md` (Turn 14 entry appended)
