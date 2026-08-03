# Convergence Brief — LV Voice Experience Redesign + MVP for 2026-08-04

**Status:** CONVERGENCE (awaiting operator rulings Q1–Q5, then → spec → build)
**Date:** 2026-08-03 (evening; teachers start on the app 2026-08-04)
**Inputs converged:**
1. Operator framing (this session): Ask = Perplexity; Observe = dedicated lens updater;
   general chat = LLM-independent action layer, not ready.
2. Claude design take (this session): mic never navigates — it fills the surface it's on;
   Observe is the product; command layer = redirect-and-prefill, zero LLM in action path.
3. Claudia Canu lens: one voice system, multiple voice rails (Observe / Ask / Prepare /
   Command); "the regression is that every mic lost its contract and became Ask —
   restore the contracts."
4. UX designer lens: three-mode voice (Observe / Ask / Prepare-Act); mic label + behavior
   change by location; global mic → small command palette, never straight to Ask;
   Observation voice is the flagship, not Ask.
5. Teacher Slack thread (Christi, Olga, Federica): 10 profile categories populated by
   teacher feedback directly; strategies-trialed with outcome; strengths/traits as report
   evidence; multi-teacher triangulation; intervention teachers who don't know the student.
6. Code reality audit (2026-08-03, `static/index.html` + `src/web.py`) — see §2.

---

## 1. Converged design (all four lenses agree — no ruling needed)

**D1. The mic never navigates; the surface decides the allowed action.** Voice is an input
method, not a feature. Same mic icon everywhere; label and contract change per view.
Teachers must never wonder "what will this mic do?"

**D2. The product hierarchy — the student lens is the center, not Ask:**
- **Observe** = write trusted evidence (flagship voice path)
- **Student Profile** = inspect/organize evidence
- **Ask** = read-only reasoning over evidence (Perplexity-like: answers with receipts —
  GIR + tier badges + OBS- citations; says when it doesn't know; may *suggest* actions,
  never silently performs them; explicit boundary: "To save new evidence, use Observe.")
- **Prepare** = create materials from evidence (generation happens INSIDE Prepare with its
  constraints; "make me a worksheet" in Ask → helpful redirect that opens Prepare
  prefilled, never a chat-generated document — the 59s/GIR-0.0 hallucination gate stays)
- **Command voice** = move between these without learning the app structure —
  deterministic, LLM-free routing; NOT ready; own spec later (see §5).

**D3. Observe voice contract (the most polished path):**
- Launched from a student profile → default to that student.
- Launched from Observe → require student detection or confirmation; ambiguous → ask,
  **never guess** (extends the invented-clinical-defaults defect class: no guessed
  students, ever).
- Speech → structured extraction (`/api/observe/classify`: Christi's categories via
  `support_category`, strategy trialed + outcome, strengths, CEFR/SEL) → **review card
  before save** → teacher confirms/edits/discards → lens updates → toast + spoken
  confirmation. Teacher stays the author of the record (this is also the honest answer to
  Olga's triangulation ask: every entry is attributed teacher feedback, not AI inference).
- Never route observation text through Ask.

**D4. Speak-and-commit is retired.** No voice path writes an observation without a review
step. (Current `/api/voice/act` observation intent saves immediately — see §2. UX lens
allowed a very-high-confidence skip; Claudia lens says always review. **Converged: always
review for now** — skip-at-high-confidence is a later, data-justified relaxation.)

**D5. The failure diagnosis, agreed verbatim across lenses:** the old two mics weren't
wrong in shape, they were under-built (capture wasn't structured+confirmed; STT itself was
broken — since fixed). The universal companion then made voice carry intent that the view
already carried. Restore per-surface contracts on the same speech infrastructure
(`voiceRuntime.captureLocalStt` chokepoint stays the single STT gate).

---

## 2. Code reality (audit 2026-08-03, grounds the MVP scope)

| Surface | Mic today | Handler | Routes to | Live? |
|---|---|---|---|---|
| Global voice companion | `#vc-mic` (index.html:731) | `toggleVoiceCompanion()` :1171 | `/api/voice/act` → intent dispatch | **YES — the only live mic** |
| Observe view | `#mic-status` badge only ("use the voice companion mic") :1761 | `toggleObserve()` :1130 **orphaned** | would prefill `#obs-text` | NO |
| Ask view | `#ask-voice-status` text only :2514 | `toggleAsk()` :1122 **orphaned** | would submit to Ask | NO |
| Student lens / Prepare | none | — | — | NO |

- The regression mechanism: per-surface buttons were never mounted; `handleVoiceActResult`
  (:1222) is the sole transcript consumer; its "question" default lands in Ask via
  `switchView("ask")` (:1309) — so in practice "every mic goes to Ask."
- **Voice observation saves have NO review step**: `/api/voice/act` → immediate
  `ObservationCapturePipeline` write (web.py:2795). The propose-confirm machinery exists
  and is good — `/api/observe/classify` (web.py:3487, `writes_made:0`,
  `teacher_confirmation_required:true`) — but is only reachable from the typed form's
  "Suggest fields" button (:1830).
- Backend needs ~nothing for the MVP. This is a frontend contract-restoration, not a
  rebuild.

---

## 3. MVP for tomorrow (target: desktop-v0.2.33, UI contract v100→v101)

Smallest change that restores the contracts, kills speak-and-commit, and is safe to ship
the night before day one:

**MVP-1 — Mount the Observe mic (flagship).** Real button in the Observe view.
`captureLocalStt` → transcript into `#obs-text` → auto-invoke `suggestObservation()`
(existing classify propose-confirm) → teacher reviews the prefilled form → existing save
path (`/api/observe/capture`) → existing toast. The review card is the Observe form
itself — zero new UI, reuses the v100 toast contract.

**MVP-2 — Mount the Ask mic (dictation only).** Real button in the Ask view →
transcript into `#ask-input` → normal `submitAskText` path. Nothing else. `toggleAsk()`
already exists; mount and wire.

**MVP-3 — Defang the global companion.** `#vc-mic` keeps its signal-based dispatch
(`/api/voice/act` intent classify is 0–2ms, LLM-free) but every destination becomes
**land-prefilled, never commit**:
- observation intent → open Observe with form prefilled + suggestions (NOT direct save)
- question intent → Ask, as today
- generate intent → Prepare redirect, as today
And it says where it's going ("This sounds like an observation — opening Observe.").
*Alternative under ruling Q1: replace dispatch with a 3-choice palette, or hide the
companion for day one.*

**MVP-4 — Per-surface labels.** Observe: "Capture observation". Ask: "Ask a question".
Companion (if kept): "Speak — I'll open the right place." `applySttAvailability()`
continues to gate/dim all of them off `/api/voice/probe`.

**MVP acceptance checks:**
- A1: Mic in Observe never leaves Observe; produces a reviewable prefilled form; nothing
  saved before the teacher taps Save.
- A2: Mic in Ask never saves anything; transcript lands in the question box.
- A3: No voice path commits an observation without the review step (grep: no voice
  transcript reaches `/api/observe/capture` without a form interaction).
- A4: Companion dispatch announces its destination; observation intent opens Observe
  prefilled instead of writing.
- A5: STT-unavailable state dims every mounted mic with plain-language text (existing
  probe contract, re-verified on new buttons).
- A6: Existing tests green; teacher-readiness harness re-run ≥ current 16/19.

**Explicitly deferred (post-tomorrow, own specs):**
- Prepare mic ("describe what you need") and student-profile mic ("add evidence for this
  student") — highest-value next increments, but new surface work.
- Command Voice as a real command grammar (finite verb list, fuzzy-name disambiguation
  UX, honest no-match: "I didn't catch a command — here's what I can do", never a silent
  fall-through to Ask). Design the verb list from a week of observed teacher demand.
- Ask→Prepare prefill payload (student/goal/output-type carried into Prepare fields, not
  just a view switch).
- Multi-teacher triangulation + background-doc upload to profiles (Olga) — product
  features, not voice.
- Review-card skip at very high confidence; remember-last-mode on the palette.
- Category/lens-scoped mic ("add evidence to this category") and report-evidence
  dictation.

---

## 4. Open questions — operator ruling needed

- **Q1 — Global companion for day one:** (a) keep, defanged dispatch that announces +
  prefills (MVP-3 as written, least change); (b) replace with 3-choice palette (UX lens
  favorite, slightly more UI work tonight); (c) hide it for day one, only per-surface
  mics. Recommendation: **(a)** tonight, palette (b) next cycle.
- **Q2 — Ship timing vs Chip QA:** Chip's 0.2.32 pass
  (`dev/PROMPT_CHIP_QA_0.2.32_2026-08-04.md`) tests the CURRENT voice-act direct-save
  (Round 2 step 5 expects voice save + toast, no review step). Options: (a) Chip tests
  0.2.32 as-is tonight, we ship 0.2.33 after her pass; (b) build now, update her prompt
  (step 5 becomes review-card flow), she tests 0.2.33 — one QA pass covers what teachers
  actually get tomorrow. Recommendation: **(b)** if build lands within ~2–3 h, else (a).
- **Q3 — Voice review-card confirmation:** on voice-initiated saves, is toast-only enough
  after teacher taps Save, or keep spoken confirmation too? (Spoken exists today on the
  voice-act path.) Recommendation: keep spoken confirmation — it's the hands-busy
  affordance.
- **Q4 — `voiceLastStudent` 120s context memory** (index.html:1471): keep for the
  companion's student detection, or drop with speak-and-commit gone? Recommendation:
  keep — it only prefills now, and prefill+review makes a wrong guess harmless.
- **Q5 — Version/QA mechanics:** 0.2.33 tonight retires 0.2.32 same-day (one-live-version
  rule). Full local suite still deferred per operator sequencing (after next two feedback
  rounds); CI test gate on the bump push is the de-facto suite run.

---

## 5. North star (unchanged by MVP)

Voice helps teachers do three things faster: **capture evidence, retrieve evidence, turn
evidence into next-step teaching artifacts.** Observe voice is what makes LV different
from a generic AI chat app. Everything in §3 is a step toward the §1 design, nothing is a
detour.
