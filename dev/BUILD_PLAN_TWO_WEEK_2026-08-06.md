# Two-Week Build Plan — Still I Rise Sync (2026-08-06 → 2026-08-20)

**Source:** `Title_ Still I Rise × Mission Canvas — _ Transcript.txt` + `_ Recap.txt`
(both in `~/Downloads/`), plus Olga's channel questions and the Rime deprecation email
forwarded this morning. Next sync: Thu 2026-08-20 (bi-weekly). Commitment made on the
call: "I'll see you in two weeks with all that stuff built, and I'll respond in Slack
to the questions from Olga."

This doc is a plan, not a diff — nothing below is built yet. Every root cause was traced
to actual code (file:line), not guessed, so the plan can go straight to implementation
without a re-discovery pass.

---

## 0. Answer Olga's 4 questions first (owed in Slack, before next week per the call)

### Q1 — "The file upload does not work"
**Confirmed root cause.** `/api/students/ingest` → `docpipe/extract.py:_normalize()`
(`src/lingua_viva/docpipe/extract.py:104-116`) only accepts `.md` / `.txt` / `.csv` /
`.pdf`. A real school class list is almost always `.xlsx` or `.docx` — neither is
supported, so the upload fails with `unsupported format for extraction: ...`. The file
picker (`static/index.html:2169`) has no `accept` filter, so nothing stops her from
trying the exact format that's guaranteed to fail.
**Answer to give her now:** "Confirmed bug, not you — today it only reads plain text/CSV/
PDF, not Excel or Word. Fix is in this build window. Workaround right now: save the class
list as CSV (File → Save As → CSV in Excel/Sheets) and re-upload — that path already works."

### Q2 — "We uploaded the file where the class list should be uploaded and the system
misinterpreted it for students, how can we delete this false data?"
**Confirmed root cause.** The same `/api/students/ingest` job (`src/web.py:2310-2350`)
auto-creates a **permanent, real student profile** for every name it detects at
confidence ≥ 0.7 — with zero teacher confirmation. The deterministic name-detector
(`_detect_students()`, `docpipe/extract.py:322-351`) scores every capitalized
First-Last bigram at 0.99 confidence ("verbatim"), so a class list — which by definition
*is* a list of First Last names — creates one real student record per name, silently.
**Answer to give her now:** "Also confirmed, also a real bug — it should have asked you
to confirm each name before creating anything, and it didn't. Cleanup right now: Students
→ open each wrongly-created student → Archive (soft-delete, one at a time, sorry — bulk
delete is on this build list). Tell me roughly how many got created and I'll walk you
through it live if it's more than a couple." **Do not tell her to re-upload the same file
until Q1's format fix ships** — same failure mode either way.

### Q3 — "How much setup is required before there is generation of output?"
Honest current answer, not aspirational:
1. Install the app (Mac/Windows installer from linguaviva.art).
2. Ollama must be installed + have one model pulled (the wizard offers to do this; if
   skipped, Ask/Prepare/materials generation return an honest "no model" message instead
   of guessing — never a silent failure).
3. At least one real observation logged per student before **Ask** or **Prepare** can say
   anything specific about that student — with zero observations, the app correctly says
   "not enough data" rather than inventing something (Claudia's own test on the call
   confirmed this works, and she called it out as reassuring, not broken).
4. Nothing else is required to start — no roster upload, no Drive connection, no config
   file editing. Students can be added one at a time by hand from minute one.
This belongs in a one-page "what to expect" note for the 2-3 pilot teachers — see §4 below.

### Q4 — "Can we possibly add grades 1-12?"
**Confirmed root cause, and it's a design bug, not a missing feature.** Grade validation
in `create_student` (`src/web.py:4204-4223`) checks the new grade against whatever grade
bands happen to exist in the *curriculum content* (`CurriculumService().get_overview()`),
not against an independent list of valid school grades. So a student's allowed grade is
accidentally capped by how much curriculum material has been loaded — today that's
roughly G1-G5. Fix: decouple these — a canonical G1-G12 (or PYP/MYP/DP-labeled) grade list
for the Add Student dropdown, independent of which grades currently have curriculum
content behind them. **Yes, straightforward — on this build list.**

---

## 1. Two other items from this morning (not from the call, but time-sensitive)

### Perplexity key issue seen on Claudia's own machine this morning
Root cause: `_perplexity_api_key()` (`src/web.py:1962-1969`) checks a `providers.json`
entry first, then `PERPLEXITY_API_KEY` env var — but **nothing in the app ever writes a
`perplexity` entry to `providers.json`.** The only "connect a provider" UI
(`/api/provider/connect`, `SUPPORTED_PROVIDERS`) is for reasoning-model providers
(Ollama/OpenAI/Groq/Mistral), not Perplexity. So in practice Perplexity has only ever
worked when someone manually exports the env var before launching — which the packaged
desktop app never does for a real teacher. This is why it looked configured in dev and
broke on a clean morning launch.

### Rime key + the Arcana deprecation email
Root cause: `_rime_api_key()` (`src/web.py:1909-1910`) is **env-var only** — no
`providers.json` fallback exists at all, so there is currently zero durable way for a
teacher to configure natural TTS. Same desktop-bootstrap gap as Perplexity, one step worse.
**On the deprecation email specifically:** the Rime call in this codebase sends
`RIME_MODEL_ID` defaulting to `"mistv3"` (`src/web.py:2588`), not `"arcana"` — so the
Aug 15 2026 Arcana→Coda cutover as described in the email does not appear to touch this
integration. Flagging this as a low-confidence "probably fine" rather than closing it
outright — worth one line to Rime support confirming `mistv3` isn't also affected before
treating it as resolved.

**Fix for both:** add a real Settings section (Ask / Voice) that persists both keys to
local config and wires `_perplexity_api_key()` / `_rime_api_key()` to read it, so this
stops depending on someone manually exporting env vars.

---

## 2. Two-week build plan, in priority order

Grouped by what's ready to build now vs. what's gated on someone else's input — don't
build the gated items ahead of that input arriving.

### Ready to build now (no external input needed)

| # | Item | Why this priority | Size |
|---|---|---|---|
| 1 | **Fix class-list upload** — accept `.xlsx`/`.docx` in the ingest pipeline (or, faster: clear client-side format guidance + a one-click "convert to CSV" note until real parsers are added) | Olga is blocked on this *today* | S–M |
| 2 | **Require confirmation before roster-import creates students** — multi-name imports must show a review list (name + confidence) before any profile is created; single low-confidence names already get this via `needs_confirmation` (`src/web.py:2344-2350`) — extend the same gate to the high-confidence bulk-roster case | Prevents Q2 from recurring the moment Q1 is fixed | M |
| 3 | **Bulk delete/undo-by-import** — a "remove everything created by this import" action tied to `source_id`, on top of the existing one-by-one `DELETE /api/students/{id}` archive | Olga needs this *now* even before #2 ships, to clean up the current mess | S |
| 4 | **Grades 1-12** — decouple Add Student's grade dropdown from curriculum-band coverage | Small, isolated, explicitly requested | S |
| 5 | **Perplexity + Rime key persistence** — Settings section, wired into both lookup functions; verify the `mistv3`/Arcana question with Rime support | Both integrations are silently non-functional on a clean install today | M |

### Gated on input already requested on the call — check Slack before starting

| # | Item | Waiting on | Size |
|---|---|---|---|
| 6 | **Confidential/CPS category + Drive-folder routing** | Christianna's exhaustive abuse-signs list (she committed to sending it); also her preference on naming — not "confidential," something softer ("personal" or similar) since one note isn't a concern until it's a pattern | M |
| 7 | **Manifesto's 9 traits on the student profile** (self-worth, self-discipline + critical thinking, emotional intelligence, self-organization, grit, social intelligence, entrepreneurship, integrity) | Manifesto doc is already in Slack ("Mission Canvas Docs") — this one can actually start now, re-reading that doc; not blocked, just sequenced after #1-5 | M |
| 8 | **Trait mapping** (observation text → one of the 9 keys) | Agreed approach on the call: optional dropdown (explicit) + regex/keyword best-guess fallback when teachers skip it (they will skip it — Christianna was explicit teachers won't add steps); needs real classroom trial-and-error to tune, not a one-shot build | M, then ongoing tuning |
| 9 | **Rename parent summary → "student summaries"** | Not gated, just small — bundle with #7 | XS |
| 10 | **Rubric generator** | Explicitly "let me know what you want" — no build without their input on what/how to assess | Unscoped until input arrives |
| 11 | **Slack bot integration** | Explicitly "give me one concrete use-case" — Olga hadn't even read the doc yet as of the call | Unscoped until input arrives |

### Suggested day-by-day shape (10 build days, 2026-08-06 → 2026-08-20)

- **Days 1-2:** #1 (upload fix) + #3 (bulk undo) — unblocks Olga immediately, answers Q1/Q2 with code instead of just words.
- **Days 3-4:** #2 (confirmation gate) + #4 (grades 1-12) + #5 (Perplexity/Rime settings).
- **Days 5-7:** #7 (manifesto fields) + #9 (rename) + #8 (trait mapping v1 — dropdown + regex fallback).
- **Days 8-9:** Buffer for whatever Christianna's abuse-signs list and Slack use-case answer turn into (#6, #11) if they land in time; otherwise keep polishing #8's mapping accuracy — Christianna already framed this as iterative.
- **Day 10:** Demo prep for the 2026-08-20 sync — same discipline as the internal demo rehearsal doc: pick real, honest things to show, don't overreach.

---

## 3. What NOT to build this cycle

- Rubric generator content/structure — no input yet.
- Slack bot — no concrete use-case yet.
- Automatic daily Drive push — floated as a "maybe," not requested; the manual
  import/export loop already works and wasn't flagged as broken.
- A 5th Drive category beyond what Christianna asks for — wait for her list before
  guessing at field names or categories.

## 4. Side deliverable: one-page "how much setup" note

Olga specifically asked for something simple enough to hand to 2-3 pilot teachers with no
training. Turn §0 Q3's answer into a literal one-pager (install → Ollama check → add a
student → log one observation → try Ask) and drop it in the shared Slack doc alongside
the manifesto file. This directly serves her stated goal ("very, very simple line of
instruction") and costs almost nothing once the app-side fixes above are confirmed
working.
