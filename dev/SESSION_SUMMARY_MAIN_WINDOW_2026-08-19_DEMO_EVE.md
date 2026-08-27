# Session Summary — Main Coordination Window, 2026-08-19 (demo eve)

**Role of this window:** spec/prompt author, release-chain preflight, push verifier,
and coordinator between the build window (PC1), the independent tester (PC2/Mac,
teacher on screen), and the orchestration agent. Written retrospectively 2026-08-22.

**The clock:** live demo 2026-08-20 morning — the real teacher, her real school files,
two workflows: lesson-content diversification (Prepare → 3 tiers) and student lens
creation scoped to her class only.

---

## 1. Authored the v1 fix wave documents

From the findings audit (`FINDINGS_REAL_DATA_PIPELINE_AUDIT_2026-08-19.md`, 16 findings
C1–C5/L1–L10) and the NEXT_STEPS sequencing doc:

- **`dev/SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.md`** — binding build order:
  Phase 0A (always-preview import, preview-never-writes lock) → Phase 0B (labelled
  corpus + scorer + sealed holdout) → STEPs 1–9 (lens pipeline; L9 structure
  preservation as keystone) → STEPs 10–12 (content honesty). §5 prohibitions, §6
  acceptance gates, §8 open operator rulings, §9 stop points (demo-min = Phase 0 →
  STEP 4 + STEPs 8/10).
- **`dev/PROMPT_LV_UNIFIED_REAL_DATA_FIX_BUILD_2026-08-19.md`** — build prompt with
  the "five ways the system lies about itself" section (failures-as-success, wrong
  failure reasons, gates that can't fail / flat 0.99, dual normalizers, no
  denominator), current-state stakes, hard constraints (Phase 0 first, privacy,
  sealed holdout, .deb quartet untouched, no blocklist growth, one normalizer),
  verified code anchors.
- The operator amended both externally: the STANDING rule **"Build for the teacher,
  never for the demo"** (demo sets the clock, never the target) replaced my demo
  framing, and Drive `drive.file` per-file scope context was added.

## 2. Authored the independent test protocol (PC2)

**`dev/INDEPENDENT_TEST_PROTOCOL_REAL_DATA_2026-08-19.md`** — for a tester on a
separate machine acting as a real teacher: install from the live site only, fresh
`~/.lingua-viva`, record environment/versions; §2 per-file expected-count scorecard;
§3 backend capture around every step (store counts before/after, preview-writes-nothing
check, model-used + timing per call, verbatim warnings, logs); §4 the five lying
patterns to hunt; §5 test script (Arc A lenses A1–A10, Arc B content B1–B5, Arc C
hostile pokes); §6 report format with a Contradictions (screen vs backend) section as
the most-valuable output.

## 3. Lane 3 release-chain preflight (read-only)

Verified the chain healthy: auto-release.yml push-trigger → `workflow_call` to
desktop-release.yml → pin-site job requires every asset HTTP 200 before advancing the
`docs/index.html` pin → Pages deploy; a failed build leaves the site on the previous
good release.

**Found the .deb-quartet trap before it fired:** four uncommitted WIP files
(`auto-release.yml`, `desktop-release.yml`, `desktop/package.json` deb hunks,
`desktop/electron/deb-after-install.sh`) add `LinguaViva.deb` to the must-200 gate
while no build produces a .deb — committing them would make every release succeed but
the site never advance. Issued a pre-push gate; verified the quartet appeared in ZERO
of the build's 16 commits.

Also answered orchestration questions (per-STEP time estimates: code-bound vs
model-bound; parallel-safety rules for a shared repo) and printed the combined-8+10
verification battery (3 runs — happy path / forced failure / `LV_REASON_MODEL`
override — each double-counting both STEPs' clauses).

## 4. Verified the v1 push → desktop-v0.2.65 live

Background watcher on build push `ee077707` → run 32310216708 all green →
`desktop-v0.2.65` released → site pin advanced (`5f969926`) → all assets 200 →
cache-busted site check. Six of seven AGENTS.md steps verified from this window;
step 7 (app-reported version) delegated to PC2 — later found impossible (Finding 7:
no UI surfaces the version; became fix F4).

Triple-checked the build agent's closure report and flagged two real issues:
- v0.2.64 (the rollback target) was deleted before PC2 had validated 0.2.65;
- the "35 her-class lenses / 0 FP" claim — which cracked open the denominator problem.

## 5. The denominator saga — the session's defining error chain

- My original audit figure "~39" for the teacher's class was wrong: it counted names
  across BOTH side-by-side class columns. It propagated into the labelled corpus, so
  the build validated 35 "her-class" lenses as "0 FP" against wrong labels.
- Operator hand-count (screenshot) corrected to 20 hers / 41 grade. I issued a
  STOP-THE-CLOSE diagnostic to the build window and corrected all five documents at
  the source (findings, spec, prompt, protocol, INDEX).
- The independent run then corrected it AGAIN: her class is **18** (sections 17 + 19).
  Both prior counts were inflated by the same structural defect that caused the bug —
  stacked group tables under the roster.
- **Resolution:** counts are no longer trusted from any document. The v2 spec (§1)
  replaces numbers with a procedure: fixed extractor prints the roster-block names per
  class column → human confirms → label sealed → scorer verdict meaningful.
- Lesson recorded: the instrument (scorer) was sound; the calibration (labels) was
  wrong. Only human counts caught it — lying pattern #5 lived inside our own test
  documents, twice.

## 6. Kept testing unblocked in parallel

- Ruled v0.2.65 sufficient for the full PC2 protocol despite the known column defect;
  printed a known-defect AMENDMENT (only A4/A5/A6 poisoned) so testing proceeded while
  the fix was planned.
- Verified the Mac `.dmg` download was genuine v0.2.65: sha256 byte-identical to the
  release digest, signed (TeamIdentifier XWT7RB624U), notarization Accepted → GO.
- Diagnosed the Linux AppImage failure: Electron SUID sandbox fatal
  (`setuid_sandbox_host.cc`); `--no-sandbox` launches and stays up. Means broken OOTB
  on Chromebooks too. Operator ruling: note it, don't fix tonight (launcher fix next
  cycle).
- Diagnosed the OAuth popups during the build (`Error 400: redirect_uri_mismatch`) as
  a Web-type vs Desktop-type OAuth client — operator console fix, not code; also
  flagged non-hermetic tests firing real OAuth.

## 7. Prepared the naked fix window, then processed the PC2 report

Printed the window-prep prompt (read-order with ground-truth override, quartet
exclusion, ff-pull handling, corpus location, green baseline, then STOP and wait).

**PC2 report** (`~/Downloads/BASELINE_REPORT_v0.2.65_2026-08-19.md`, tester = the
teacher herself): verdict MIXED. The run's headline positive: **zero screen-vs-backend
contradictions** across 16 snapshots / 14 traces — the five lying patterns are dead;
remaining failures are capability, not candour. Three demo-blockers:

1. Importing her class fabricates children (18 → 35): stacked Music/STEAM group tables
   where each column holds a whole name get the roster's surname+firstname join rule,
   fusing two real children into one non-existent student; no per-entry remedy in the
   preview.
2. Ask invents a progress report from zero data (0 observations, 0 evidence, CEFR all
   null) and reads it aloud — hedged as "weak source" when the truth is "no data".
3. The printable packet silently re-generates (3 fresh model calls at print-preview) —
   what prints is not what was reviewed; the intermittent broken Italian she rejected
   can reappear at print time. Her verdict: "I would not hand these 3 cards to my
   students."

Also: support extraction captured ~5% of available content (honestly reported), no
Save-as-PDF fallback, no version in UI, stale auto-create copy, unit not detected,
one misclassification, broken logo.

## 8. Authored the v2 (demo-eve) fix wave documents

- **`dev/SPEC_LV_DEMO_EVE_FIX_2026-08-19.md`** — F1 roster-block segmentation
  (structural block detection; only the roster block is a creation source; join rule
  scoped to it; F1b per-entry exclude in preview), F2 zero-data refusal gate in Ask
  (code gate, not prompt guidance), F3 packet renders the STORED reviewed artifact
  with zero model calls on the print path + explicit Regenerate (converts the
  model-bound Italian-quality problem into a reviewable one), F4 surface version in
  UI, F5 fix the lying import copy, F6 time-permitting list. §1 human-confirmed-count
  procedure; §3 explicit out-of-scope; §4 constraints (quartet, ONE push, privacy,
  no blocklists, locks stay green); §5 gates; §6 report requirements.
- **`dev/PROMPT_LV_DEMO_EVE_FIX_BUILD_2026-08-19.md`** — paired build prompt: context,
  read-order, the counts-override rule, build order F1→F5, the report's
  "genuinely fixed" table repurposed as a regression lock-list, ship gates, and the
  closing rule: a truthful "not shipped" beats a hollow release on demo eve.

## 9. End state of this window

- v1 wave: shipped and live as desktop-v0.2.65; independently tested same evening.
- v2 wave: fully specified and prompted; naked window prepped; execution handed off.
  One interactive pause designed in: human confirmation of the extracted roster list
  (expected 18) before the corpus label seals.
- This window's remaining duty at handoff: post-push verification battery for the v2
  push (run watch → release → assets 200 → pin advanced → site serves new tag →
  in-app version check via F4).
- Open items deliberately deferred: Italian generation quality (model-bound),
  support-extraction depth, Linux `--no-sandbox` launcher, OAuth Desktop-type client,
  STEP 9 (§8-2 unruled), K-5 history ruling, release cleanup after validation,
  non-hermetic OAuth tests, spec §8 rulings (build ran on defaults).

**Privacy note:** no student, colleague, or school names appear in this summary or in
any document authored in this window; real-file outputs stayed local per protocol.
