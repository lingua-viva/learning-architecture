# SPEC — LV Demo-Eve Fix Wave (v2) — 2026-08-19 (night)

**Clock:** live demo tomorrow morning (2026-08-20), real teacher, real files. One build
wave, ONE push, tonight.

**Input:** independent test run of desktop-v0.2.65 (PC2, Apple M4 Max, teacher on
screen). Report: `~/Downloads/BASELINE_REPORT_v0.2.65_2026-08-19.md` — READ IT FIRST.
Do NOT commit the report; reference it by path.

**The headline from that run:** every honesty mechanism works — zero screen-vs-backend
contradictions across 16 snapshots and 14 traces. The five lying patterns are dead.
The remaining failures are failures of CAPABILITY, not candour. This spec fixes the
three capability blockers plus two cheap honesty-adjacent items. Do not break the
candour that was just won: every fix below must keep the app's self-reporting literally
true.

---

## §1 Ground truth — numbers are no longer trusted from documents

The expected count for the teacher's class has now been wrong TWICE in our own docs
(~39 in the audit; 20/41 in the 08-19 correction). The teacher's own count is **18**,
with the two Grade 3 sections at 17 + 19. The reason every document count was wrong is
Finding 1 itself: the sheets contain stacked non-roster tables that inflate any naive
column count.

**Binding rule for this wave:** no expected-count is hardcoded anywhere — not in code,
not in tests against the real files, not in the corpus labels — until it has been
confirmed by a human against the extracted name list. The acceptance procedure is:

1. The fixed extractor prints, per class column-pair, the roster-block names it found
   (LOCAL ONLY, never committed).
2. The operator/teacher confirms the list and count for her class.
3. Only then is the corpus label sealed and the scorer verdict meaningful.

Synthetic committed fixtures must replicate the STRUCTURE (§2 F1), with synthetic names,
and may hardcode their own known counts.

---

## §2 The fixes, in binding order

### F1 (P0) — Stop fabricating children: roster-block segmentation
**Report Finding 1.** Her class of 18 imported as 35; the surplus are two real
children's names concatenated into one non-existent student.

**Confirmed cause:** each K–5 sheet holds two classes side by side (cols A/B, C/D) and
THREE stacked tables per sheet:
- roster (≈rows 3–21): col A = surname, col B = first name → joining A+B is correct
- "1/2 groups for Music/Homeroom" (≈24–34): EACH column holds a complete name
- "1/2 groups for STEAM/Homeroom" (≈38–48): same
The A+B join rule is applied to all three blocks; the group tables emit fused names.

**Fix (structural, no name heuristics, no blocklists):**
1. Segment each sheet into blocks: a block boundary is one-or-more blank rows and/or a
   header/title row (a row whose cells are labels like "1/2 groups for …" — detect by
   structure: merged/single-cell row between populated blocks, not by matching specific
   words).
2. Only the FIRST block under the class-name header (the roster block) is a student
   source. Group-table blocks are never creation sources. (Match-only enrichment from
   group tables is explicitly OUT of scope tonight.)
3. The surname+firstname join applies only inside the roster block.
4. Preview shows block provenance (which rows/ranges the names came from) so a wrong
   segmentation is visible before confirm.

**F1b (should, if the evening allows):** per-entry exclude in the preview — the report
found "no per-entry remedy: create-all-35 or Cancel". Minimum viable: a click on a name
pill toggles it out of the confirm set, with the count on the confirm button updating.
This is the teacher's safety net against the NEXT structural surprise.

**Acceptance:**
- Synthetic fixture replicating the 3-stacked-tables + 2-class-columns shape: extractor
  returns exactly the roster-block names for the selected column-pair, zero fused names.
- Real file (local): extracted list confirmed by human per §1 (expected: 18).
- Class-lock test: a group-table-shaped block can never contribute to creation.
- Preview-never-writes lock stays green.

### F2 (P0) — Ask must refuse, not invent, on zero data
**Report Finding 2.** With observations 0, evidence 0, all CEFR null, support profile an
empty scaffold, Ask said the child "has been making good progress… working on basic
sentences" and read it aloud. Badged unverified/GIR 0.00 — but the hedge says "my source
is weak" when the truth is "you have no data on this student."

**Fix:** a hard gate BEFORE generation on student-scoped questions: if the referenced
student has zero observations AND zero evidence records AND no CEFR dimension set,
the answer is a refusal-with-reason, generated from a fixed honest frame (e.g. "There
are no observations recorded for this student yet — I can't describe their progress.
Add an observation and ask again."), never a model-invented progress narrative. TTS
reads the refusal. The gate is code, not prompt guidance — the model must not be able
to route around it.

**Acceptance:** test with a zero-data student asking a progress question → response
contains no progress/ability claims, states the no-data reason, still traces
`route=local`. Test with a student that HAS one observation → normal path unaffected.

### F3 (P0) — The packet prints what the teacher reviewed
**Report Finding 4 (new, worst-of-run for trust).** "Preview Printable Packet" fired
three FRESH model calls; the printed packet differed from the reviewed cards (including
different Italian). Teacher review is defeated: what is approved is not what prints.

**Fix:**
1. Persist the generated tier material at generation time (content + model + timestamp,
   keyed to the lesson).
2. Packet preview/print renders the STORED artifact. Zero model calls on the
   preview/print path.
3. New content is only produced by an explicit "Regenerate" action, which replaces the
   stored artifact and is itself reviewable before printing.

**Why this is also the Finding 3 mitigation:** the Italian defects (istituzioni/istinti,
dei→degli, rabbia/paura) are intermittent — the second run was correct. Model quality on
a 3B model is not fixable tonight; what IS fixable is making review meaningful: the
teacher regenerates until the cards are right, and what she approved is exactly what
prints. Record Finding 3 as known-open (model-bound) in the report.

**Acceptance:** generate → note trace count → preview packet → trace count UNCHANGED,
packet text byte-equal to the reviewed cards. Regenerate → new content, again stable
through print.

### F4 (P1) — Surface the app version in the UI
**Report Finding 7.** `lv:get-version` is wired in preload/main but nothing calls it.
Tomorrow morning we must verify the teacher's machine runs tonight's build — currently
impossible from the UI. Display the version somewhere always-reachable (settings pane
or topbar/footer). Smallest honest implementation wins.

**Acceptance:** UI shows the packaged version; matches package.json/release tag.

### F5 (P1) — Kill the copy that lies about behavior
**Report Finding 8.** The import box still reads "Every student gets a profile
automatically; one click undoes the whole import" — describing the 0.2.63 auto-create
model that 0.2.65 deliberately replaced with preview-first. This is the app lying about
itself again, in static copy. Replace with preview-first truth ("Nothing is created
until you review and confirm"). Also fix the xlsx not-found message that advises
"scanned PDF → try Word" for an .xlsx.

### F6 — time permitting ONLY, in this order
1. Save-as-PDF fallback for printing (Electron `printToPDF`) — Finding 6.
2. Unit detection from coursework ("Unit: Diversity and e…" present in excerpt, dropdown
   stayed empty) — Finding 8.
3. Teacher progress question misclassified `classification_domain=parent` — Finding 8.
4. Broken topbar logo — Finding 8.

## §3 Explicitly OUT of scope tonight
- Italian generation quality itself (model-bound; mitigated by F3; document it).
- Support-extraction depth (Finding 5: ~5% capture, honestly reported) — next cycle.
- Group-table match-only enrichment; spelling-drift reconciliation queue.
- Linux AppImage sandbox fix; OAuth Desktop-client (operator console task); STEP 9
  (§8-2 unruled); K-5 history ruling; release cleanup of superseded versions.

---

## §4 Hard constraints (unchanged from the v1 wave — violating any ends the run)
- The four uncommitted .deb WIP files appear in ZERO commits
  (`.github/workflows/auto-release.yml`, `.github/workflows/desktop-release.yml`,
  `desktop/package.json` deb hunks, `desktop/electron/deb-after-install.sh`).
  Hunk-isolate every commit. NOTE: F4 may need `desktop/` changes — if
  `desktop/package.json` must change, stage ONLY your hunks, never the deb WIP hunks.
- Privacy: no real student/colleague/school names in any commit, test, or report.
  Real-file runs and their outputs stay local.
- ONE push, at the end, after all gates. PUSH = live and downloadable per AGENTS.md.
- `MC_AGENT=1` on every run.
- No name blocklists; positive structural conditions only.
- Preview-never-writes and enrichment-never-grows-count locks stay green.

## §5 Verification gates (all before the one push)
1. Full suite green (`pytest -q tests/`).
2. New class-lock tests green: F1 segmentation fixture, F2 zero-data refusal,
   F3 zero-model-calls-on-print.
3. Scorer re-run against the RELABELED corpus (labels sealed per §1 only after human
   count confirmation).
4. Real-file local run: her class column-pair → extracted list printed → human confirms
   (expected 18) → confirm → store count equals confirmed count; curriculum/calendar
   still 0; 3V import does not grow the count.
5. `lv preflight` green; UI contract bumped for the UI changes (F1b/F4/F5).
6. Claudia-lens UX audit pass.
7. Push once; verify per AGENTS.md 7 steps (run green → release assets 200 → site pin
   advanced → cache-busted site check). PC2/Mac re-checks A4–A6 + the B-arc print path
   on the new build, and can now read the version in-app (F4).

## §6 Report
`dev/REPORT_LV_DEMO_EVE_FIX_2026-08-19.md` — per-fix evidence, the human-confirmed
count, scorer before/after, known-open list (Finding 3 model-bound, Finding 5, and
everything in §3). Update `dev/INDEX.md` status rows in the same commit. Also append a
correction note to `dev/FINDINGS_REAL_DATA_PIPELINE_AUDIT_2026-08-19.md`: the 08-19
"20/41" correction is itself superseded — teacher count 18; counts now flow only
through the §1 procedure.
