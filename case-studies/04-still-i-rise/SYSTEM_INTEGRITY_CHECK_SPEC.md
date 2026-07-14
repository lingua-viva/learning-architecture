# System Integrity Check Spec — Still I Rise Education Build

**Purpose**: verify, piece by piece, that everything built across the Governed RAG cycle (Turns 16-21) and the Re-Ground fix cycle (Turn 22) is actually correct, actually wired together, and actually matches what its own docstrings/journal entries claim — not just "tests are green." Tests passing proves the code does what the tests assert; this spec checks whether the tests assert the right things and whether the pieces truly connect end to end.

**Scope**: `src/education/*.py` (12 modules), the 3 shared-pipeline files they hook into (`src/pipeline.py`, `src/context_builder.py`, `src/mc_cli.py`), and every test file under `tests/` that targets these. Reference source: `case-studies/04-still-i-rise/BUILD_JOURNAL.md` (Turns 16-22) is the authoritative claim-log — every check below traces back to a specific claim made there.

**Out of scope**: do not modify any Tier-2 admin capability (none exist yet — confirm this is still true), do not touch `slack_bot.py` beyond confirming it still imports and its own tests still pass (it was explicitly not part of this cycle's build), do not attempt to fix the known `_rank_score()` ontology coverage-bias bug (documented, deferred, out of scope for this check).

**Method for each piece below**:
1. Read the module (or the relevant section) — don't rely on memory of what it "should" do.
2. Read its test file — check the tests actually exercise the claim, not just import the module.
3. Run its test file in isolation (`pytest tests/<file> -q`) and confirm the count matches what's documented.
4. Where a specific behavioral claim is made (e.g. "never force-pairs," "0 is a real achievement level," "append-only"), write one line confirming you traced the actual code path that guarantees it — not just that a test happens to pass.
5. Flag anything that doesn't match — mismatch between docstring claim and code, test that doesn't actually test the claim, silent behavior change, missing edge case — as a finding, with file:line.

---

## Piece 1 — Document intelligence stack (Turns 16-20)

**Files**: `document_parser.py`, `document_store.py`, `document_retrieval.py`

- [ ] `DocumentParser`: confirm PDF chunking produces correct heading attribution and that table rows never leak into prose chunks (the two bugs the Turn 16 fix specifically targeted — re-derive this from `_is_heading`/chunk-boundary logic, don't just trust the test name).
- [ ] `_redact()`: confirm PII redaction patterns actually match the claimed categories (names, emails, phone numbers per Turn 17/18 journal text) and that `needs_review` is set correctly by `_needs_review()`.
- [ ] `DocumentStore`: confirm `add_chunks()`/`search()` round-trip through SQLite-vec with real embeddings (no mock), and that `EmbeddingUnavailableError` is caught where documented (Turn 18: "degrades safely, doesn't fail the query") — trace this into `DocumentRetriever.retrieve()` and confirm it returns `[]` on that exception rather than propagating.
- [ ] `DocumentRetriever`: confirm domain-gating is real — an out-of-scope domain must produce zero store calls, not just an empty result (check this distinction matters: was it verified via a call-count assertion, or just an output assertion?).
- [ ] `document_parser.py` docstring says PDF ingestion restricts to `curriculum`/`organizational` doc types and blocks `student-records` — confirm that restriction is enforced somewhere in this cycle's code (`mc_cli.py`, see Piece 2) and not just documented as an intention.
- [ ] Run `pytest tests/test_document_intelligence.py -q` — confirm 7/7 and that each of the 7 tests maps to a distinct claim above (list which test covers which claim; flag any claim above with no corresponding test).

## Piece 2 — Pipeline wiring (Turns 18-19)

**Files**: `src/pipeline.py`, `src/context_builder.py`, `src/mc_cli.py`

- [ ] `Pipeline.__init__`: confirm `document_retriever` is optional, duck-typed, defaults to `None`, and that omitting it reproduces prior behavior exactly — find the specific test(s) that assert zero document-block output when no retriever is injected.
- [ ] Step 2 RETRIEVE: confirm the retriever is called with `(safe_query, classification.domain, k=3)` as documented, and that this is domain-scoped (re-verify Piece 1's gating claim from the pipeline's calling side, not just the retriever's own tests).
- [ ] `context_builder.py`: confirm the `## Retrieved Document Excerpts` block only appears when chunks exist, and that `[NEEDS HUMAN REVIEW]` is surfaced per-chunk from `needs_review`, not a blanket flag.
- [ ] `mc_cli.py`: confirm `mc ingest --type=student-records` is actually refused (find the `ALLOWED_DOC_TYPES`/`BLOCKED_DOC_TYPES` check) and that `_document_retriever()` returns `None` when no store file exists yet (avoids a stray SQLite file / wasted embedding call per Turn 19 journal — confirm this guard is a file-existence check, not something more fragile).
- [ ] Confirm `src/pipeline.py` still has zero import of anything under `src/education/` — the documented boundary ("shared pipeline never imports domain code").

## Piece 3 — `content_differentiator.py` (base + Turn 22 adaptation fix)

- [ ] Base template path (`_generate_tier`, `assign_tier_for_student`): confirm tier-assignment logic and trauma guardrails (`TRAUMA_UNSAFE_LABELS`, `_check_trauma_safety`, `PERSONAL_REFLECTION_OPT_OUT`, `FOUNDATIONAL_MAX_SENTENCE_WORDS`) are byte-for-byte unchanged from pre-Turn-22 — this was an explicit operator instruction ("keep as-is"); diff-check if git history is available, otherwise re-derive from the docstring's own claims.
- [ ] `generate(lesson, source_chunks=None)`: confirm `source_chunks=None` (the default) produces identical output to calling with no `source_chunks` argument at all — i.e., confirm no existing caller anywhere in the repo (`grep -rn "ContentDifferentiator().generate\|\.generate(lesson"` across `src/`) was silently changed by this signature edit.
- [ ] `_adapt_tier_from_source`: confirm foundational tier's sentences actually respect `FOUNDATIONAL_MAX_SENTENCE_WORDS` after simplification (not just before) — trace `_simplify_sentence`, don't trust the test name alone.
- [ ] Confirm every prompt produced by `_adapt_tier_from_source` (all 3 tiers) passes through `_check_trauma_safety` — same guardrail as the template path, not a bypassed parallel check.
- [ ] `ContentPack.source_mode`/`source_provenance`: confirm `source_mode` is literally `"adapted"` only when `source_chunks` was non-empty after joining, and `"generated"` otherwise — check the actual blank/whitespace-only edge case (a `source_chunks` list of chunks with empty `"text"` values) falls back to `"generated"`, not a silently broken adapted pack.
- [ ] `generate_from_documents()`: confirm it duck-types against `.retrieve(query, domain, k)` with no hard import of `document_retrieval.py` (`grep -n "^from\|^import" src/education/content_differentiator.py`).
- [ ] Run `pytest tests/test_content_differentiator.py -q` — confirm 22/22, and confirm at least one test exercises the retriever-returns-empty fallback (not just retriever-returns-chunks).

## Piece 4 — `student_lens.py` + `teacher_guide.py` (Turn 22 conflict-aware grouping fix)

- [ ] `student_lens.py` append-only guarantee: confirm `avoid_pairing_with` is the *only* new mutable (replace, not append) field added this cycle, and that it does NOT go through `append_observation()` — `grep -n "avoid_pairing_with" src/education/student_lens.py` and trace `set_avoid_pairing_with()` to confirm it's a direct `UPDATE`, never an `INSERT` into `observations`.
- [ ] Confirm the existing append-only guarantee for `observations` (the actual audit trail — RTI tier history, CEFR snapshots) was not weakened by this change — re-run the original append-only tests (`test_observations_are_append_only`, `test_manual_rti_tier_change_is_logged_not_overwritten`) and confirm they still pass unmodified.
- [ ] `_conflicts(a, b, avoid_map)`: confirm symmetry by hand — a conflict declared only by `b` against `a` must still block the pair when checking from `a`'s side. Don't just trust `test_build_groups_conflict_is_symmetric`; read the boolean expression itself.
- [ ] `build_cross_level_groups()`: confirm the "never force-pairs" claim by tracing the actual loop — is there any code path where a conflicting pair could still end up in the same `Group`? Check the `idx = next(...)` generator-based skip logic specifically for an off-by-one or first-match bug.
- [ ] Confirm unplaced students are surfaced, not silently dropped — trace that every student in the roster ends up in either a `Group.student_ids` or `unplaced`, with no student unaccounted for (write a quick check: for a given roster, `len(groups)*members + len(unplaced) == len(roster)` — note group sizes vary 1-3, so verify via ID-set union instead of count).
- [ ] `TeacherGuide.to_markdown()`: confirm the "Suggested Groups" and "Needs Manual Grouping" sections only render when non-empty (no empty headers in output when there are no groups/no unplaced students).
- [ ] Run `pytest tests/test_student_lens.py -q` → confirm 18/18. Run `pytest tests/test_teacher_guide.py -q` → confirm 10/10.

## Piece 5 — `assessment_generator.py` (Turn 22 provenance fix)

- [ ] Confirm the 0-8 achievement band scale is real (not 1-8) — `band_descriptors` must include a `"0"` key with real descriptor text, and `TIER_TARGET_BAND` must map tiers to bands that never include `"0"` as a target (targets are scaffolded expectations, not floor).
- [ ] Confirm `criteria` (4 generic codes A-D) are applied identically across all 3 tiers — same criteria dict object/keys regardless of tier, per the "criterion-referenced, not tier-referenced" claim in the docstring.
- [ ] Confirm the task reuse claim: for every tier, `TierAssessment.task_prompt` must equal `pack.tiers[tier]["tasks"][-1]["prompt"]` verbatim — no re-wording, no LLM call in between (re-derive from `AssessmentGenerator.generate()`, confirm there's genuinely no text transformation between pack and assessment).
- [ ] Confirm `is_adapted` detection (`getattr(pack, "source_mode", "generated") == "adapted"`) correctly falls back to `"generated"` for any `ContentPack` built before this field existed (i.e. a hand-constructed pack without `source_mode` set) — this is the actual backward-compatibility guarantee, verify it's not just an assumption.
- [ ] Confirm `IB_COMPLIANCE_NOTE` vs `IB_COMPLIANCE_NOTE_ADAPTED` text is honest — neither note may claim verified subject-specific IB criterion wording (re-read both constants literally, confirm the "NOT verified subject-specific" disclosure survives in both variants).
- [ ] Run `pytest tests/test_assessment_generator.py -q` → confirm 13/13.

## Piece 6 — Modules NOT touched this cycle (regression-only check)

**Files**: `observation_capture.py`, `trend_analysis.py`, `weekly_recommendation.py`, `parent_report.py`, `morning_brief.py`, `access_control.py`, `slack_bot.py`

- [ ] These were explicitly not part of the Turn 16-22 build. Confirm none of them import anything from the modules touched this cycle in a way that could have silently broken (`grep -rln "content_differentiator\|teacher_guide\|assessment_generator\|student_lens" src/education/observation_capture.py src/education/trend_analysis.py src/education/weekly_recommendation.py src/education/parent_report.py src/education/morning_brief.py src/education/access_control.py src/education/slack_bot.py`).
- [ ] If any dependency is found, run that module's own test file and confirm no regression.
- [ ] Otherwise, a single confirmation that these modules are untouched/unaffected is sufficient — do not deep-audit modules outside this cycle's scope.

## Piece 7 — Whole-system checks

- [ ] Full suite: `MC_AGENT=1 python3 -m pytest -q tests/` — record pass count, compare against the last known-good baseline (262/262, Turn 22). Any count other than 262 (or a higher number if new tests were added since) is a finding.
- [ ] `mc health` (with `MC_AGENT=1` set) — record score, compare against last known-good baseline (84/84, 100%, Turn 22).
- [ ] Cross-check every numeric claim in `BUILD_JOURNAL.md` Turns 16-22 (test counts, health scores) against what actually runs today — flag any journal claim that no longer reproduces.
- [ ] Confirm `publication-policy.md` rules (no institution names, no student names/individual data, no colleague names, no proprietary school documents) are still respected by every module's docstrings, test fixtures, and sample data added this cycle — spot-check `tests/fixtures/sample_myp_guide.pdf` and the sample chunk fixtures in `test_content_differentiator.py`/`test_assessment_generator.py` for anything that reads as real (not synthetic) institutional content.

---

## Output format

Produce one table, same shape as the original Re-Ground audit:

| Piece | Status (VERIFIED / MISMATCH / FINDING) | Evidence (file:line, test name, or trace) |
|---|---|---|

Followed by a short "Findings" list (only items that are MISMATCH or FINDING — omit VERIFIED items from prose, the table already covers them) and a one-line overall verdict: is the system as-built consistent with what the journal and docstrings claim, yes/no, with exceptions named explicitly.

Do not fix anything found during this check. This is a verification pass, not a build pass — findings get reported back for a separate, explicitly-approved fix cycle, same discipline as the original Re-Ground audit.
