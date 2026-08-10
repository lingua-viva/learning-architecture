# QA Testing Plan — Lingua Viva Teacher Readiness (2026-08-10)

**Purpose**: Full end-to-end pass of everything a teacher will touch, including
everything shipped since the 08-01 packet: safeguarding routing, parent
recommendations/reports, coursework packs, library search, PoI progression,
and honest no-model behavior. **56 checks across 14 scenarios (S, A–M).**

**Tester**: Chip (GitHub: DontWriteDown)
**App**: Lingua Viva desktop app, downloaded fresh from **linguaviva.art**
**Expected version**: desktop-v0.2.51 **or newer** (a fix release may land
tonight — record the exact version; older than v0.2.51 is itself a P1 finding)
**Local URL once running**: http://127.0.0.1:8787
**Test data**: SYNTHETIC ONLY. The two students are **Marco Bianchi** and
**Nora Rossi** — fake children invented for this packet. Never type a real
child's name. The safeguarding scenario uses invented concerning phrases about
these FAKE students — that is deliberate and safe.

---

## Note to the harness (Claude Code): read this first

- Lead the tester through the scenarios below **in order, one step at a time**.
  She replies "done" (or describes what went wrong) after each step.
- **Setup scenario S must run before everything else** — later scenarios
  depend on the two seeded students.
- **THE FRESH INSTALL ITSELF IS A FIRST-CLASS TEST.** A P0 fresh-install
  failure (`ModuleNotFoundError: No module named 'fastapi'`) was confirmed on
  Linux today (D1-P0-001). Chip is on a Mac — if her fresh install fails to
  reach health, that is the single most valuable finding of the night:
  capture the backend log (look under `~/.lingua-viva/logs/`, the app's
  Application Support folder, and Console.app), record the exact traceback
  and the setup wizard's exact wording, publish a short P0 report immediately,
  and only then decide with her whether to continue on a previously-working
  install.
- Some features are **backend-only** (no button yet): lesson materials (E),
  cohort planning (G), coursework packs (K), and some safeguarding probes (I).
  For those YOU call the local API, show her the output, and she judges by
  eye. Before calling any endpoint new since 08-01, fetch
  `http://127.0.0.1:8787/openapi.json` and confirm the path and request shape
  — do not guess payloads. If an endpoint is absent, record
  **"NOT IN THIS BUILD (version X)"** and move on.
- Voice steps: mic mis-transcription → retry twice, then paste the sentence
  into the text input and note "tested via text fallback".
- **Honest-degradation rule for judging**: if the app says a model was
  unavailable and shows a plain deterministic answer or banner, that is a
  PASS (that is the designed behavior). Pretending a model answered, or a
  raw error/traceback shown to the teacher, is a FAIL.

---

## Scenario S — Setup (harness-led, ~5 min) — checks 1–2

1. App freshly downloaded from linguaviva.art, installed, open, health OK
   (check 1 — **this is the fresh-install gate; see harness note above**).
2. Create students **Marco Bianchi** (G3) and **Nora Rossi** (G3); seed one
   observation each (check 2):
   - Marco: `During group reading, Marco helped a classmate find the right page.` (speaking, A2)
   - Nora: `Nora used full sentences to describe her weekend.` (speaking, B1)

---

## Scenario A — Google Drive Connection (checks 3–7)

| # | What Chip does | Pass looks like |
|---|---|---|
| 3 | Click "Connect Google Drive" | Browser opens the Google consent screen |
| 4 | Approve access | App shows "Connected" with her email |
| 5 | Connect a Drive folder (paste a folder URL) | Folder accepted, no error |
| 6 | Look at the folder's file list in the app | Files from that Drive folder listed |
| 7 | Upload `documents/G3_family_relationships_unit.pdf` to Drive, Import from the app | Import succeeds |

---

## Scenario B — Document → Student Lens (checks 8–11)

Uses `documents/student_record_marco_bianchi.md` (synthetic).

| # | What Chip does | Pass looks like |
|---|---|---|
| 8 | Import the Marco record with purpose **student_lens_source** | Extraction runs automatically |
| 9 | Open the extraction result | Fields visible: name, grade, level, support needs |
| 10 | Confirm some fields, reject at least one | Lens updates with confirmed fields only |
| 11 | Students → Marco Bianchi | Profile shows the newly confirmed data |

---

## Scenario C — Voice → Observation → Lens (checks 12–16)

| # | What Chip says (tap mic first) | Pass looks like |
|---|---|---|
| 12 | `Marco helped a classmate find the right page during reading` | Recognized as an observation for Marco |
| 13 | (same as 12) | Spoken confirmation, **first name only** |
| 14 | Students → Marco | The new observation appears |
| 15 | `Nora used full sentences to describe her weekend` | Same flow for Nora |
| 16 | `The student struggled with greetings` | App asks WHICH student — must NOT guess |

---

## Scenario D — Voice → Question → Answer (checks 17–18)

| # | What Chip says | Pass looks like |
|---|---|---|
| 17 | `What level is Marco at in reading?` | Answer based on his lens (spoken + shown) |
| 18 | `How should I group my students for tomorrow?` | A grouping recommendation |

Allow ~60s. Honest "no model available" degradation = PASS (see judging rule).

---

## Scenario E — Lesson Materials Generation (checks 19–24)

Check 19 by voice; 20–24 harness triggers via API (same call as the 08-01
packet: `POST /api/lesson-materials/generate`, PYP / Italian / daily routines /
A2 / 45 min) and saves the worksheets as .md files for her to read.

| # | Step | Pass looks like |
|---|---|---|
| 19 | Say: `Create a worksheet for daily routines in Italian` | App acknowledges and asks which students |
| 20 | Harness calls the API | Three tiers return: foundational / on_track / extended |
| 21 | Foundational worksheet | Word banks + sentence starters |
| 22 | On-track worksheet | Model example + independent practice |
| 23 | Extended worksheet | Open-ended prompt |
| 24 | Scan all three | **No student names anywhere** — "Marco", "Nora", "Bianchi", "Rossi" in any worksheet body = P0 |

---

## Scenario F — Drive Auto-Sync (checks 25–28)

| # | Step | Pass looks like |
|---|---|---|
| 25 | Set a Drive folder as the sync folder | Setting saves |
| 26 | Save a new observation for Marco, check Drive in browser | Updated lens .md appears in Drive |
| 27 | After Scenario E, check Drive | Worksheet files appear |
| 28 | Wifi OFF → save an observation → wifi ON | Saves locally with **no error**; file syncs after reconnect (~2 min grace) |

---

## Scenario G — Cohort Lesson Planning (checks 29–31)

Harness calls `POST /api/cohort-plans/preview` (same payload as 08-01 packet)
and shows her the teacher guide.

| # | Chip checks | Pass looks like |
|---|---|---|
| 29 | Teacher guide | Readable lesson plan with tier groupings |
| 30 | Groupings section | Students placed foundational / on-track / extended |
| 31 | Distribution section | Per-tier handout instructions |

---

## Scenario H — Basic App Health (checks 32–36)

| # | Step | Pass looks like |
|---|---|---|
| 32 | (from Setup) app launched | No errors on launch |
| 33 | Click through every sidebar tab | No crash, no blank screen, always a way back |
| 34 | Doctor / health page | Passes; no "PRIVATE_RISK" false positive |
| 35 | Observe form by hand: text + student + save | Saves with visible confirmation |
| 36 | Open Settings | Drive, voice, sync, privacy controls present |

---

## Scenario I — Safeguarding Routing (checks 37–42) — NEW, highest-stakes

**Why**: concerning observations must be routed to a restricted ledger —
never into the normal student record, worksheets, or parent materials. All
phrases below are INVENTED about FAKE students. This is the most important
new scenario in the packet.

| # | What Chip does | Pass looks like |
|---|---|---|
| 37 | Type (Observe form): `Marco said his dad hits him at home` and save | Save succeeds calmly. NO scary popup, NO error — and the harness confirms via API/logs it was routed restricted |
| 38 | Students → Marco, read his observation list | The concerning observation is **NOT visible** in his normal record/stream |
| 39 | Open the daily brief / today view (if present) | No trace of the concerning content |
| 40 | Type and save: `Marco hit the ball hard at recess and laughed` | Saves as a NORMAL observation, visible on Marco's record (benign contact phrase must not be over-flagged) |
| 41 | Harness probes `GET /api/safeguarding/restricted` as the app's default (teacher) identity | **Denied** (coordinator-only) — teacher role cannot read the restricted ledger |
| 42 | After Scenario J (parent artifacts), harness greps all generated parent/worksheet artifacts from this session | Zero safeguarding content anywhere downstream |

**Record if**: check 37 shows the content anywhere public, 38 shows it in the
stream (P0), 40 gets flagged/hidden (over-flagging = alert-fatigue finding,
P1), 41 returns data to a teacher identity (P0).

---

## Scenario J — Parent Recommendation & Report (checks 43–47) — NEW

| # | Step | Pass looks like |
|---|---|---|
| 43 | In the app, generate a parent recommendation for Marco (harness: `POST /api/parents/recommendation` if no button) | A parent-appropriate summary returns |
| 44 | Read it as if you were Marco's parent | Warm, plain language; no jargon, no internal codes, no CEFR machinery unexplained |
| 45 | Harness inspects the raw response JSON | No teacher-only keys, no severity/safeguarding fields, no other student's data |
| 46 | Generate the parent report PDF for Marco (if the route/button exists) | PDF renders, readable |
| 47 | Harness + Chip scan the PDF | Nothing from check 37's restricted observation; no Nora data in Marco's report |

---

## Scenario K — Coursework Packs (checks 48–50) — NEW

Harness calls the coursework pack API (`/api/artifacts/coursework-pack` —
confirm shape via openapi.json first), saves teacher + student copies as files.

| # | Chip checks | Pass looks like |
|---|---|---|
| 48 | Teacher copy | Complete pack; tiering visible; answers/guidance present |
| 49 | Student copy | Aligned with teacher copy but **no teacher-only keys, no answers, no student names in content** |
| 50 | Generation time | Returns within ~1 min; if enrichment is unavailable it degrades to a plain deterministic pack (that is a PASS) with no hang |

---

## Scenario L — Library Search (checks 51–53) — NEW

| # | Step | Pass looks like |
|---|---|---|
| 51 | Add/import a document into the Library (Sources view), e.g. the G3 unit PDF | Ingest succeeds, doc listed |
| 52 | Search a phrase you saw in the doc (e.g. `family relationships`) | The doc comes back, best match first |
| 53 | Search nonsense (`zzqx purple elephant`) | Graceful empty/low-relevance result — no crash |

---

## Scenario M — PoI Progression Panel (checks 54–56) — NEW

| # | Step | Pass looks like |
|---|---|---|
| 54 | Students → Marco → find the PoI progression panel | Panel renders (phases / trend / next target) |
| 55 | Compare with what you know about Marco (2 observations tonight) | Content is plausibly based on his data, not lorem-ipsum |
| 56 | Open the same panel for Nora | Renders with HER data — no bleed-over from Marco |

---

## UX Feedback Template (Chip fills in at the end)

1. What worked?
2. What didn't work, or looked wrong?
3. What was confusing?
4. What would a real teacher quit over?
5. **Would you hand this to Claudia's teachers tomorrow? If not, what's the one thing to fix first?**
6. Feature requests (not bugs — keep the list going)

---

## Severity guide

- **P0** — teacher cannot use the app, data loss, or a privacy/safeguarding
  leak (student name in generated materials, restricted content visible
  anywhere downstream, spoken full names, real-looking data where it
  shouldn't be)
- **P1** — a listed check fails but there's a workaround; over-flagging of
  benign phrases (alert fatigue)
- **P2** — cosmetic, confusing wording, papercuts
- **FR** — feature request (not a bug)
