# Harness Prompt — The Full Audit (Claudia, real-time, 2026-08-29)

## To Claude Code: read this entire file before starting

You are running the **fullest QA audit of Lingua Viva to date** with
**Claudia Canu Fautré** — Italian-immersion K-5 IB PYP teacher, curriculum
architect, and the product's real user. She is not a QA engineer. Frame
everything in classroom terms (students, observations, lesson prep), never
APIs or state variables. She thinks in Italian pedagogical frameworks — use
her language where natural (PoI = Programme of Inquiry, UdA = learning unit,
CEFR levels, Indicazioni Ministeriali).

**Acceptance frame (non-negotiable):** she audits as ANY teacher — fresh
download from linguaviva.art, zero special access, zero fixes mid-session.
If you are tempted to patch something so the audit can continue, don't:
record the finding and route around it.

### Version gate — first check of the night

App must be **desktop-v0.2.72 or newer** (topbar version badge or
`/api/health` `.version`). If older: file it as **P0-VERSION**, stop the
audit, and tell her the release didn't ship. Do not audit v0.2.71 — most of
the new-surface scenarios below don't exist in it.

### Real-time reporting protocol (what makes this audit different)

- Create `qa/2026-08-29_claudia-full-audit/REPORT.md` at session start with
  the version table (app version, platform, date, tester) and empty findings
  sections (P0 / P1 / P2 / FR / PASS log).
- **File each finding the moment she reports it.** ID format:
  `P0-1`, `P1-1`, `P2-1`, `FR-1`, sequential. Quote her words — do not
  paraphrase judgments into softer language.
- After each scenario, append one line to the PASS log:
  `Scenario X: n/m checks passed — [one-line verdict in her words]`.
- If a **P0** lands, commit the report immediately
  (`git add qa/2026-08-29_claudia-full-audit/REPORT.md && git commit -m "qa: P0 finding"`)
  so the finding survives anything, then continue if she can.
- Give her a running count at each scenario boundary ("14 checks done,
  2 findings so far").

### Pacing and judging

- One step at a time. Wait for her reply before moving on.
- **Honest-degradation rule:** if the app says a model was unavailable and
  shows a plain deterministic answer or banner, that is a **PASS** — that is
  designed behavior. Pretending a model answered, a raw error, or a
  traceback shown to a teacher is a **FAIL**.
- Voice steps: mis-transcription → retry twice, then paste the sentence as
  text and note "tested via text fallback".
- Backend-only features (no button yet): YOU call the local API
  (`http://127.0.0.1:8787`), show her the output, she judges by eye. Before
  calling any endpoint, fetch `http://127.0.0.1:8787/openapi.json` and
  confirm the path and request shape — never guess payloads. Absent
  endpoint → record **"NOT IN THIS BUILD (version X)"** and move on.
- **Synthetic data only**: Marco Bianchi (G3, A2 speaking), Nora Rossi
  (G3, B1 speaking). The safeguarding scenario uses invented concerning
  phrases about these FAKE students — deliberate and safe.

---

## Part 1 — The established surface (~70 min)

Run **all scenarios S and A–M** from
`qa/teacher-readiness-packet/QA_TESTING_PLAN.md` (56 checks, 14 scenarios),
in order, under the rules above. That file is the authority for those steps —
read it fully before starting. Notes for this run:

- Scenario S (setup, seeded students) must run first; everything depends on it.
- The fresh install is a first-class test — if install fails, capture logs
  (`~/.lingua-viva/logs/`, Application Support, Console.app), file P0,
  publish immediately, then decide together whether to continue.
- Where the 08-10 plan says "Chip", read "Claudia".
- Some checks marked backend-only in the 08-10 plan may have UI now
  (lesson materials gained buttons in v168). Prefer the UI path; note when
  a formerly backend-only feature now has a working button — that's a PASS
  worth logging by name.

**Break point here.** Offer her a pause before Part 2.

---

## Part 2 — Everything shipped since 08-10 (~50 min)

### Scenario N — Lesson-plan artifact loop (v168) — checks 57–62

57. Prepare → **Create Lesson Plan** for Marco's group (any topic she'd
    really teach). A structured plan renders — not raw JSON, not a wall of
    text. She judges: usable at 8am Monday?
58. **Preview Lesson Plan** shows the rendered structured preview.
59. Use the **targeted revision field** — she asks for one concrete change in
    plain language ("più attività orali"). The revision lands where asked,
    nothing else silently changes.
60. **PDF save/print** works from the stored plan; the PDF is legible and
    she'd hand it to a colleague.
61. Italian correctness: she reads the generated plan for language errors —
    any wrong Italian is a finding (P2 each, P1 if pedagogically misleading).
62. Empty-source honesty (v177): with NO teaching source selected, Prepare
    **blocks generation** and says why, instead of generating from nothing.

### Scenario O — Document → student lens import (v170/v176) — checks 63–67

63. Students → the document upload panel. Upload a synthetic class document
    (make one together in the session: a plain-text or .docx list with fake
    fields for Marco/Nora).
64. Extraction preview shows fields per student with **plain classroom
    language** for how each match was made — NO raw confidence percentages,
    no method tokens. Any raw number leaking through = P1 (regression of the
    v165 rule).
65. Preview is preview-only — nothing written to lenses until she confirms.
66. **Apply** writes the reviewed extractions; student lens shows them.
67. She uploads something wrong on purpose (a recipe, a lesson plan). The app
    fails politely, in her terms, with no traceback.

### Scenario P — The honesty surfaces (v172–v175) — checks 68–73

*The app now catches itself. She verifies the catch, not the polish.*

68. Ask a student-named question with real observation history behind it.
    If the answer carries sources/grounding → fine. If it carries **no**
    signal and **no** sources, it MUST show the **"unverified · no grounding
    signal"** badge (v173). A confident, unbadged, sourceless answer about a
    child = **P0** — this is the fabrication catch, the highest-stakes check
    of the night.
69. Ask about a zero-observation student (create one fresh). The app hedges
    honestly — "not enough information" is a PASS, invented specifics a FAIL.
70. The Ask header states the **real route** (v174): with web search
    unconfigured it must NOT say "answers come from the web"; it says
    local / not configured / "route not confirmed". Header and answer badge
    must not contradict each other.
71. Assess: no empty rubric panel rendered; grade-with-no-units path is
    disabled with a named route to Plan (v172).
72. Safeguarding (v175, invented phrase about FAKE Marco): the concern saves
    as a restricted record and the badge reads **"Restricted record — not
    yet routed to a person"** — it must NOT claim a coordinator or anyone
    was notified. The copy names the school's human safeguarding process.
73. She scans every surface that mentions the safeguarding item (student
    view, exports, parent report from Scenario J): the restricted content
    appears nowhere it shouldn't.

### Scenario Q — The Claudia UX pass (v177) — checks 74–78

*These were built from her feedback. She's auditing her own asks.*

74. Home shows a **next-best-action strip** — and the action it suggests is
    actually sensible for the current state. A dumb suggestion is a finding.
75. Observe: after saving an observation, the **selected learner is
    preserved** — she saves two observations for Nora back-to-back without
    reselecting.
76. Parent summaries require the **review checklist before copy/print** —
    she cannot export an unreviewed summary.
77. Privacy view shows a **log-driven verdict** when external Ask calls
    exist: she makes one external-eligible query, then checks Privacy
    reflects reality, not a static reassurance.
78. Her open verdict: does the app now behave the way she asked on each of
    these? Anything that misses the spirit of her request = FR with her
    wording.

### Scenario R — Closing sweep — checks 79–82

79. Version badge still correct; no session-long degradation (app responsive
    after ~2 hours of use).
80. Quit and reopen: students, observations, lesson plans, safeguarding
    restriction all survive restart.
81. She names the best thing and the worst thing of the night (verbatim,
    into the report).
82. Ship verdict, her words: would she put this in front of a colleague
    tomorrow — yes / no / with-caveats-listed.

---

## Closing the session

1. Finalize `REPORT.md`: counts by severity, round-by-round pass log, her
   two verbatim verdicts (81, 82).
2. Commit and push to the `claudia` branch:
   ```
   git checkout -b claudia 2>/dev/null || git checkout claudia
   git add qa/2026-08-29_claudia-full-audit/
   git commit -m "qa: Claudia full audit 2026-08-29 — real-time report"
   git push -u origin claudia
   ```
3. Tell her what was filed, thank her properly — this is the fullest audit
   the product has ever had, and she did it as its real user.
