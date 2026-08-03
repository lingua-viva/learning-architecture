# Lingua Viva — Operator-Ruled Build Brief
**Supersedes:** Convergence Brief — LV Voice Experience Redesign + MVP for 2026-08-04
**Date:** 2026-08-03 (evening)
**Hard deadline:** teachers begin using the app 2026-08-04
**Status:** RULED — operator has decided. This is a build brief, not a discussion document.

---

## 0. How to read this document

The prior convergence brief proposed a **frontend voice-contract restoration**: mount per-surface mics, kill speak-and-commit, defang the global companion. That analysis was accepted as correct, but the operator has **re-ordered the priorities**. Voice is no longer the primary MVP.

> **The pivot in one sentence:** the app cannot ship with empty tabs and a working microphone. It must be able to ingest real documents from Google Drive and the local filesystem, process them locally, and populate real artifacts — lesson plans, lenses, student profiles, assessments. Voice is how a teacher *updates* those artifacts, not how they get created.

Sections marked **[P0]** must work tomorrow. **[P1]** is wanted tomorrow if time allows. **[P2]** is explicitly deferred. §8 lists questions the operator has *not* answered — do not guess on these.

---

## 1. The pivot: what changed from the prior brief

| Prior brief said | Operator ruling |
|---|---|
| MVP = mount Observe mic + Ask mic + defang companion | MVP = **document ingestion and artifact generation**. Voice is secondary |
| "Backend needs ~nothing for the MVP" | True for voice. **False for the actual MVP** — the Drive/file/local-processing pipeline is the work |
| Ask = read-only reasoning over the teacher's own evidence | Ask = **Perplexity only**. External information, cited sources, **no personal data leaves the machine** |
| Prepare = create materials from evidence | Prepare = **RAG over real files**. Find an existing lesson plan in Drive/local, modify it. Nothing generative-from-scratch |
| Command voice deferred | Still deferred, but the target shape is now specified (§7.1) |
| Always review before save (D4) | Operator dissents — see §8.1. Save must also **write back to Google Drive** so other teachers see it |

**Accepted without change:** §2 code reality audit (the regression mechanism, the orphaned handlers, the missing review step on `/api/voice/act`). All line references below are from that audit and are assumed still valid.

---

## 2. Priority stack

```
P0-A  Document pipeline: Drive/local → ingest → process locally → populate artifacts → render in app
P0-B  Observe: dictation → LLM parses to JSON structure → editable in place → saves → syncs to Drive
P1    Ask: voice-first Perplexity with spoken summary, text transcript in Ask tab, no redirect
P2    Everything else (command grammar, other-tab mics, triangulation, palette)
```

Operator statement on effort: *"I don't care if I have to work all night. We need to get at least the artifact creation from files and drive folders done today."*

---

## 3. [P0-A] Document pipeline — the actual MVP

This is the capability the whole product depends on and the one furthest from done. Operator: *"That is what I have been trying to create from the beginning... we are very far from being there."*

### 3.1 Required data flow

```
Google Drive  ──┐
                ├──►  bring into local machine
Local files   ──┘         │
                          ▼
              process locally (or PII-wash with a separate model
              before any external call)
                          │
                          ▼
              populate REAL documents locally
                          │
                          ▼
              read local documents and render them in-app
                          │
                          ▼
              write artifacts back to Google Drive (shared visibility)
```

### 3.2 Non-negotiable constraints

1. **100% grounded in real data.** Operator: *"be grounded in the real data at 100% otherwise it is useless."* No invented content. This extends the existing invented-clinical-defaults defect class.
2. **No manual entry.** Operator: *"No teacher will want to manually fill in anything."* Any flow that requires a teacher to type structured data from scratch is a failed flow.
3. **Slow is acceptable; wrong is not.** A local model may run for a long time in the background. Design for long-running background jobs, not request/response latency. Getting it right beats getting it fast.
4. **PII never leaves.** Local processing by default. If an external model is used, a separate model washes PII first.
5. **Empty on install.** All fields ship empty. There is no seed or demo data. The only way data enters the app is through file ingestion or teacher input.

### 3.3 Per-tab ingestion requirement

All eight tabs need file-map + Drive ingest. The pattern is identical; only the artifact type differs.

| Tab | Ingestion action | Produces |
|---|---|---|
| 🌅 Daily | from file path | daily view populated from real plan/roster data |
| 📋 Plan | "plan lessons from file path" | unit + grade structure derived from the source document |
| ✏️ Prepare | "prepare activities from file path" | activity/material variants (see §3.4) |
| 👁️ Observe | lens scaffolds created from documents | lenses the teacher then updates (see §4) |
| 👤 Students | "add students from file path" | student profiles |
| 📊 Assess | from file path / from prior student work | assessments |
| 💬 Ask | — (no file ingest; external only, see §5) | — |
| 👨‍👩‍👧 Parents | from file path | parent-facing artifacts |

**Operator emphasis:** *"That is our core function that has to work by tomorrow."*

### 3.4 Prepare — specific behavior

Prepare is **RAG, not generation**. Explicitly scoped:

1. Teacher chooses a file on Drive or Desktop.
2. From that file, **grade and unit are already derived** — not asked for.
3. Per lesson plan, **three tracks are generated** as slight variations of the lesson plan that already exists in the source. Not three new lesson plans — three differentiated variants of the real one.
4. Nothing else. Operator: *"That is already a lot."*

The existing 59s / GIR-0.0 hallucination gate stays in force.

---

## 4. [P0-B] Observe — dictation to editable JSON

Operator: *"If one thing needs to work tomorrow that is it."*

### 4.1 Required behavior

1. **Mic mounted in the Observe view.** Real button, not the current `#mic-status` badge (index.html:1761). The orphaned `toggleObserve()` (:1130) is the starting point.
2. **Conversational dictation to transcription.** The teacher talks naturally. Transcript accumulates — this is not a single-utterance capture. Route through the existing `voiceRuntime.captureLocalStt` chokepoint (single STT gate, do not add a second path).
3. **Teacher says "save."** Only then does the LLM act.
4. **LLM parses the transcript into the JSON structure.** The model decides which fields the content belongs in — Christi's categories via `support_category`, strategy trialed + outcome, strengths/traits, CEFR/SEL. Reuse `/api/observe/classify` (web.py:3487; `writes_made:0`, `teacher_confirmation_required:true`), currently reachable only from the typed form's "Suggest fields" button (:1830).
5. **Rendered result reads normally** — the same human-readable presentation as today.
6. **Every field is clickable and editable in real time.** This is a hard requirement, not a review-then-commit gate.
7. **Save writes the lens.**
8. **Lens syncs to Google Drive**, visible to other teachers. See §8.1 — this is the part the operator flagged as missing.

### 4.2 Why this matters beyond Observe

Operator: *"We need to get this right and it will likely be the format for all other tabs."* Treat the Observe JSON-parse-and-edit pattern as the reference implementation. Other tabs will copy it.

### 4.3 The dependency that is easy to miss

Operator: *"This information does not come from nowhere. The core ability here is still find file, create lenses by yourself [the app creates them], then and only then will the teachers update them."*

**Observe is not a blank-page tool.** The app must first generate lens scaffolds from ingested documents (§3). The teacher's voice input *updates* an existing lens. A mic pointed at an empty lens is not the product.

### 4.4 Retire speak-and-commit

`/api/voice/act` currently writes directly via `ObservationCapturePipeline` (web.py:2795) with no review. That direct-save path is removed. Voice transcript must reach `/api/observe/capture` only after a form interaction.

---

## 5. [P1] Ask — voice-first Perplexity, no redirect

### 5.1 Scope

Ask is **external information retrieval only**. It does not reason over student evidence. It does not generate materials.

Representative queries:
- "What are some good lesson plan ideas around [topic]?"
- "What are some suggestions for helping kids with dyslexia learn to read?"
- "What are strategies for a student with ADD in a language immersion classroom?"

**No personal information leaves the machine on any Ask call.**

### 5.2 Required behavior

| Element | Requirement |
|---|---|
| Button label | **"ASK"** — not "Mic". With a few example questions displayed underneath |
| Backend | Perplexity only. Whatever Perplexity returns is what the teacher gets. No post-processing layer |
| Response mode | **Voice-first.** Spoken TTS in real time from the Perplexity answer |
| Response length | One-paragraph summary, then *"Would you like to hear more?"* Set a Perplexity call parameter to cap length unless more is requested |
| Interrupt | Teacher can stop playback by clicking the ASK button again, or by saying "stop" |
| Text output | Full text answer prints in the Ask tab conversation view |
| **Navigation** | **No redirect.** The teacher is never moved to the Ask tab. They go there when they choose to, to read the conversation |

The no-redirect rule is the key departure from current behavior: `handleVoiceActResult` (:1222) currently calls `switchView("ask")` (:1309) on its question default. That auto-switch is removed.

Reference for the text rendering: `dev/assets/ask-render-reference-2026-08-03.png`

### 5.3 Redirect logic removed generally

The prior brief's "helpful redirect that opens Prepare prefilled" is **not** in scope. Ask does not route anywhere. It answers, speaks, and prints.

---

## 6. Operator rulings on Q1–Q5

| # | Question | Ruling |
|---|---|---|
| Q1 | Global companion: keep-defanged / palette / hide | **Conditional.** Build the Perplexity + ASK button + Ask-tab text population with no redirect → operator wants it. Combined with Q3, the effective ruling is: **per-surface mics only (Observe + Ask); no global dispatch companion for day one.** See §8.2 |
| Q2 | Ship timing vs Chip QA 0.2.32 | **Not answered as asked.** Operator redirected: the pivot is document access and processing; *"we cannot get to tomorrow without that."* See §8.3 |
| Q3 | Voice review-card confirmation: toast-only vs spoken | **Not answered as asked.** Operator scoped instead: *"Right now voice in Observe + mic 'Ask' button with chat populate in Ask tab only. We will build out the other interactions later."* See §8.4 |
| Q4 | Keep `voiceLastStudent` 120s context memory (index.html:1471) | **Keep.** ("Sure.") |
| Q5 | Version/QA mechanics for 0.2.33 | **Deprioritized.** *"I don't care if I have to work all night. We need to get at least the artifact creation from files and drive folders done today."* Version mechanics do not block the build |

---

## 7. [P2] Deferred — do not build now

### 7.1 Command voice (target shape, for later)

Operator sees this as the simplification layer, not the current build. Recorded so the eventual spec has the intent:

- *"Add observation for Marco"* → Observe tab opens, mic starts.
- *"Create assessment for Nora based on her last assignment"* → goes to Drive, finds Nora's most recent assignment by date, creates an assessment that can be reviewed and edited in real time.

Constraint: **build it tab by tab.** Deterministic, LLM-free routing. Finite verb list. Honest no-match ("I didn't catch a command — here's what I can do"), never a silent fall-through to Ask.

### 7.2 Also deferred

- Prepare mic and student-profile mic
- Ask→Prepare prefill payload
- Multi-teacher triangulation; background-doc upload to profiles (Olga's ask)
- Review-card skip at high confidence; remember-last-mode
- Category/lens-scoped mic; report-evidence dictation
- 3-choice command palette

---

## 8. Unresolved — do not guess

### 8.1 D4 dissent needs clarification
The brief ruled "always review before save." The operator wrote: *"I disagree with this. Not only does this have to update the lens... that lens has to be saved to Google Drive where it is shared."*

This reads as an **addition** (Drive sync is missing) rather than a true rejection of the review step — especially since §4.1 elsewhere requires fields be *"clickable and changeable in real time,"* which implies review. **Assumed interpretation: keep the edit-before-commit behavior, and add Drive write-back.** Confirm before building a direct-save path.

### 8.2 Global companion disposition
Q1's answer addresses the Ask/Perplexity feature, not the three options offered. Q3's scoping ("Observe + Ask only") implies the global `#vc-mic` (index.html:731) is out for day one. **Assumed: remove or hide the global companion.** Confirm — the alternative is a defanged announce-and-prefill dispatch.

### 8.3 Chip QA sequencing
Chip's pass (`dev/PROMPT_CHIP_QA_0.2.32_2026-08-04.md`) tests the current direct-save voice flow, which this brief removes. Round 2 step 5 will fail against the new build. Either her prompt is updated or her pass tests a version teachers will not receive. **No ruling given.**

### 8.4 Spoken confirmation on Observe save
Still open: after the teacher taps Save, is a toast enough, or is spoken confirmation also required? The prior recommendation was to keep spoken confirmation as the hands-busy affordance.

### 8.5 Likely terminology slip
Operator's closing line: *"Lets start with TTS in Observe and an LLM that populates a JSON structure."*

Observe needs **STT** (speech-to-text / dictation). **TTS** (text-to-speech) is what Ask needs for spoken Perplexity answers. §4 is written assuming **STT in Observe**. Flag if that assumption is wrong.

---

## 9. Acceptance criteria

**P0-A — Document pipeline**
- A1: A teacher can select a Drive folder or local file and the app ingests it without manual field entry.
- A2: Ingested documents produce real, populated artifacts (lesson plan, lens, student profile, or assessment) rendered in-app.
- A3: No artifact content is invented. Every generated field traces to source-document content.
- A4: Processing runs in the background and survives long durations without blocking the UI.
- A5: No PII reaches an external endpoint.
- A6: Fresh install shows all tabs empty.

**P0-B — Observe**
- A7: Mic mounted in Observe; never navigates away from Observe.
- A8: Conversational dictation accumulates; parse occurs only on "save."
- A9: Parsed output renders human-readably and every field is editable in place.
- A10: Saved lens writes back to Google Drive and is visible to other teachers.
- A11: No voice transcript reaches `/api/observe/capture` without a form interaction.

**P1 — Ask**
- A12: ASK button labeled "Ask" with example questions visible.
- A13: Answers come from Perplexity only; no personal data in the request payload.
- A14: Spoken one-paragraph summary with "hear more" continuation.
- A15: Playback stoppable by button or by saying "stop."
- A16: Text prints in Ask tab; **the view never auto-switches.**

**Regression**
- A17: STT-unavailable state dims every mounted mic with plain-language text (`applySttAvailability()` off `/api/voice/probe`).
- A18: Existing tests green; teacher-readiness harness ≥ 16/19.

---

## 10. North star (agreed, not yet reached)

Voice helps teachers do three things faster: **capture evidence, retrieve evidence, turn evidence into next-step teaching artifacts.**

Operator: *"This is the north star, I agree, but we are not there. Let's start with [STT] in Observe and an LLM that populates a JSON structure. That is already a lot. Then if we can do the Perplexity get-information experience that would be great."*

---

## 11. Scope warning for whoever builds this

The prior brief's MVP was a few hours of frontend work. **This brief is not.** §3 (Drive ingest → local processing → artifact generation → Drive write-back) is a pipeline, and §4.3 makes Observe *depend* on it — the mic has nothing to update until lenses exist.

If the full pipeline cannot land before teachers start, the honest fallback order is:

1. **One tab, end to end.** Pick the single highest-value ingestion path (Students-from-file or Plan-from-file) and make it genuinely work, rather than half-wiring all eight.
2. **Observe dictation → JSON → edit**, operating on whatever lenses exist by then.
3. **Ask/Perplexity**, which is independent of the pipeline and can ship in parallel.

Shipping one real end-to-end path beats shipping eight partial ones on day one.
