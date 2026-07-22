# Lingua Viva Happy State — P0 Experiences

**Date**: 2026-07-20
**Governing pattern**: `mission-canvas/dev/VOICE_HAPPY_STATE_P0_2026-07.md` (MC's voice happy-state doc), adapted here for LV's actual interaction surface.
**Purpose**: Define exactly what the teacher sees, types, and reads back, for each P0 experience running through the LV web app — the interaction-layer equivalent of MC's voice script.

---

## Why This Isn't a Voice Doc

MC's happy-state doc scripts spoken audio because MC has a voice surface (VIU resolution, TTS, silence budgets). **LV has no voice output.** The only audio-adjacent surface confirmed in the codebase is the browser's native `SpeechRecognition` API used once, for dictating observation text in the Observe view (`static/index.html`, `startSpeech()`) — on-device transcription, no TTS, no Rime, nothing external.

So this document scripts the **screen interaction sequence** instead: what the teacher clicks/types, what state the UI shows while working, and the exact copy that lands. Where MC has "silence budget," this doc has "response budget" — and unlike MC's voice doc, most of LV's timing figures are **not** formally specified anywhere in code. Each budget below is marked either **(enforced)** — a real timeout/limit found in source — or **(proposed, unverified)** — a reasonable UX target with no code backing it yet. This distinction is preserved deliberately rather than presenting invented numbers as fact.

---

## P0-EXP01: Install

**Not a screen experience.** Install is a terminal action (`curl -fsSL .../install.sh | sh` or `install.ps1`). No web UI involved. The teacher's first UI moment is P0-EXP02.

**Files**: `install.sh`, `install.ps1`

---

## P0-EXP02: First-Run Setup

### User does:
Opens the app for the first time (via `lv-launch` desktop shortcut, or browses to `http://127.0.0.1:8787`).

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | Role modal (blocking) | "🌱 Lingua Viva" / "I am a:" / buttons: "I am a teacher", "I am a coordinator" | Modal must appear before any other UI paints | `static/index.html:437-443`. Stored to `localStorage["lvRole"]`, gates which nav items render. |
| 2 | Home view renders | "Good morning." + today's plan, or "Set up your schedule in Settings → My Schedule to see today's plan." if no schedule saved | Immediate — client-side conditional, no network call | `static/index.html:605-606` |
| 3 | (Optional) Settings → provider connect | Text fields: provider name, API key | Test call before save; on failure, connect is rejected | `src/web.py:provider_connect()` — validates key with a lightweight test call before persisting to `~/.lingua-viva/config/providers.json` |
| 4 | Health badge | Doctor status surfaces on Health view if anything needs attention | — | Not blocking; teacher can work before checking health |

### Screen complement:
Role modal is a true blocker (no dismiss without choosing). Everything after is default-local — no provider key required to start using Ask/Prepare/Observe with Ollama.

### Response budget:
- Role modal → visible: **immediate** (static HTML, no fetch) — **(enforced by page structure)**
- Provider key test call: **no documented timeout found** — **(proposed, unverified)**: should fail within ~5s rather than hang the Settings form

### What the teacher must never see:
- Any view rendering behind the role modal before a role is chosen
- A provider "connected" state without the test call having actually succeeded
- Any external network call before the teacher has done anything (LV defaults to local/Ollama)

---

## P0-EXP03: "Why did you answer that way?" (Why view)

### User does:
Clicks "Why?" on a chat message in Ask, or navigates to the Why nav item directly.

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | View header | "Why" / "Every query is processed locally. No query text is stored, only a hash, route, sources, and timing." / badge "external calls: 0" | Renders on nav click, no wait | `static/index.html:919` |
| 2 | Trace detail | route badge, "tokens N", "external N" | On trace click | `static/index.html:924` |
| 3 | Underlying record | classification node, confidence, model used, duration, source citations, trace_id | — | `src/lingua_viva/traces.py`, `src/web.py:why()` |

### Screen complement:
This is the whole experience — there is no separate voice/screen split. The claim "no query text is stored" is enforced in code: `src/lingua_viva/privacy_log.py:log_event()` calls `event_hash()` (SHA-256) on the query text before persisting anything — the raw string never reaches disk via this path.

### Response budget:
- Nav click → Why view painted: **immediate, no fetch required for the header** — **(enforced, static render)**
- Trace list fetch: **no documented timeout** — **(proposed, unverified)**: <1s given it's a local NDJSON/SQLite read

### What the teacher must never see:
- Raw query text anywhere in a trace record (only the hash)
- A trace claiming `external calls: 0` for a query that actually left the machine — this must be architecturally impossible, not just cosmetically hidden

---

## P0-EXP04: "What left this machine?" (Privacy view)

### User does:
Clicks the Privacy nav item.

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | View header | "Privacy" / "Lingua Viva is built for local teacher work." / badge "all local" | Immediate | `static/index.html:947` |
| 2 | Summary counters | "No external calls" (0 count shown), total_queries_local, student_blocks, ai_attribution_stripped, observations_saved_locally | Fetched from `/api/privacy` | `src/web.py:privacy_events()` |
| 3 | Event log | Last 25 events, each timestamped and typed (e.g. `student_data_blocked`, `ai_attribution_stripped`) | — | `src/lingua_viva/privacy_log.py` |

### Screen complement:
Same as EXP03 — one surface, no split.

### Response budget:
- `/api/privacy` fetch: **no documented timeout** — **(proposed, unverified)**: local read, should be <500ms

### What the teacher must never see:
- A nonzero external-call count without a corresponding explanation of what specifically left and why (there's no case where this should happen at all in the current build — reasoning is local-only)
- Event log entries containing raw student names, addresses, or other patterns that `redact_runtime_text()` is supposed to catch

**Correction (LV P0 improvement cycle, 2026-07-20)**: this document originally described the `external calls: 0` badge as "backed by architecture, not display logic" without having verified that claim against the code. It was false in one real scenario: `src/lingua_viva/privacy_log.py::privacy_summary()` hardcoded `"external_calls": 0` as a literal, even though `ReasoningEngine._call_model` (`src/lingua_viva/reasoning.py`) has a real code path to openai/groq/mistral once a teacher connects a provider (EXP02). The badge would have read 0 regardless of whether an external call actually happened. Fixed: `_call_model` now logs a real `external_call_made` privacy event whenever it routes to an external endpoint, and `privacy_summary()` counts those events instead of hardcoding 0. Live-verified with a mocked external HTTP call: counter moved 0 → 1 for an external route, stayed 0 for the default local Ollama route.

---

## P0-EXP05: "What do you know about me?" (Profile view)

### User does:
Clicks the Profile nav item.

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | View header | "Your Teaching Profile" / "Everything Lingua Viva knows about this local teacher workspace." / badge "local only" | Immediate | `static/index.html:972` |
| 2 | Summary | role, grades taught, observation count, students tracked, reflections, trace count, file map summary, storage location (`~/.lingua-viva/`) | Fetched from `/api/profile` | `src/web.py:profile()` |
| 3 | Export | Download button → full JSON (students, traces, privacy events, revision log, filemap) | — | `src/web.py:profile_export()` |
| 4 | Clear | Requires typed confirmation "clear-all-data" | Irreversible | `src/web.py:profile_clear()` |

### Screen complement:
Same single-surface pattern. Unlike MC's voice version (which deliberately summarizes and hands the floor back), LV's Profile view shows everything at once because there's no voice-vs-screen split to manage — screen carries the whole load here.

### Response budget:
- `/api/profile` fetch: **no documented timeout** — **(proposed, unverified)**

### What the teacher must never see:
- An export that's missing data the summary counters claim exists
- A "Clear" action that fires without the typed confirmation string

---

## P0-EXP06: The Observation Moment (input-side protection)

### User does:
Selects a student in Observe, either types or clicks the mic (🎙️) to dictate: e.g. "Marco self-corrected passato prossimo, used essere correctly in context." Tags CEFR dimension/level/direction. Saves.

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | View header | "Capture Observation" / "Record or type a short teacher note and attach it to a local student lens." / badge "local only" | Immediate | `static/index.html:724` |
| 2 | Mic active | Browser's native SpeechRecognition UI (no LV-authored copy — this is the OS/browser's own indicator) | On-device only | `static/index.html` `startSpeech()`; falls back to a "speech unavailable" state if the browser doesn't support it |
| 3 | Save | Classify → governance gate check → PII sanitizer audit → append to lens → recalc CEFR/RTI/SEL | — | `src/education/observation_capture.py` |
| 4 | Result | "Saved" / badge "Saved locally. Not uploaded. Not shared." / badge "Domain: observation" / observation ID + the saved transcript echoed back | — | `static/index.html:770` |

### Screen complement:
Same surface. The transcript IS echoed back in the result panel — this is intentional (the teacher needs to confirm what was captured), unlike MC's hard-block pattern which explicitly forbids echoing the sensitive payload. **This is a real architectural difference, not an oversight**: LV's model is "this content was never eligible to leave the machine in the first place" (`observation_capture.py`'s `assert_never_external()` raises if a `blocks_external` classification ever reaches an external-routing code path — and no such code path exists), rather than MC's "catch it and refuse before it's used." There is no code path capable of sending observation content externally, so echoing it back locally carries none of the risk that echoing a bank account number back would.

### Response budget:
- Save → result rendered: **no documented timeout** — **(proposed, unverified)**: classification + sanitizer audit + SQLite write should be well under 1s; no network call in this path

### What the teacher must never see:
- Any network request fired during Observe capture (verifiable: DevTools network tab should show zero outbound calls other than the initial page load)
- A save that succeeds without the "Saved locally. Not uploaded. Not shared." badge
- An `AssertNeverExternal` exception surfaced as a raw stack trace instead of a clean error — this exception existing at all means a code path was reachable that shouldn't be; it's a defense-in-depth check, and it firing is itself a bug worth escalating, not routine UX

---

## P0-EXP07: The Parent Message Moment (output-side protection)

### User does:
In Parents view, selects a student + a home-support focus (e.g. "creative quiet workspace"), clicks generate.

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | View header | "Parent Recommendation" / "Draft a parent-safe message for teacher review." / badge (warn) "Review before sending. No AI attribution in final message." | Immediate | `static/index.html:885` |
| 2 | Generating | Draft assembled from student lens + local Manuale citations | — | `src/education/parent_report.py` |
| 3 | Privacy strip | Student names → "your child"; any "AI suggests" / "language model" / "generated by AI" phrasing stripped | — | `src/web.py:_strip_parent_output()` (lines 266-289) |
| 4 | Result | Subject line + body + 2-3 home activities + source citation | — | `src/web.py:parent_recommendation()` |

### Screen complement:
Single surface. The warn badge is the LV equivalent of MC's boundary-naming moment — it's shown *before* generation, not after, so the teacher knows review is required going in, not as an afterthought.

### Response budget:
- Generate → draft rendered: **no documented timeout** — **(proposed, unverified)**; this path calls the local model (Ollama), so it inherits whatever LV's model-call budget is elsewhere (see EXP08's 25s enforced timeout as the nearest documented analog)

### What the teacher must never see:
- A draft with the student's actual name still in it
- A draft containing "AI", "language model", "generated", or similar attribution phrasing that the strip function is supposed to catch
- A draft presented as ready-to-send rather than ready-to-review (the badge copy must stay attached to the output, not just the empty-state view)

---

## P0-EXP08: The Activity Pack Moment (draft/create)

### User does:
In Prepare, selects grade + unit, optionally types a topic, clicks generate.

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | View header | "Activity Generator" / "Create a three-level activity pack for the selected grade and unit." | Immediate | `static/index.html:674` |
| 2 | Generating | `Generating...` (literal placeholder text in the output panel) | — | `static/index.html:702` |
| 3 | Model call | Local reasoning generates 3-tier pack (foundational, on-track, extended) | **25s timeout, enforced** | `src/web.py:query_endpoint()` uses `timeout_seconds = payload.get("timeout_seconds") or 25`; on timeout: `"Local reasoning timed out. Check Ollama, then try again."` |
| 4 | Result | Tasks + learning objectives per tier + CEFR language + source citation | — | `src/education/content_differentiator.py` |

### Screen complement:
Single surface, progressive: the "Generating..." placeholder is the only in-flight state shown — there's no partial/streaming render the way MC streams REASON tokens sentence-by-sentence. LV's generation is request/response, not streamed.

### Response budget:
- Generate → "Generating..." shown: **immediate (client-side, before fetch resolves)** — **(enforced)**
- Model call → result or timeout: **25s hard timeout** — **(enforced)**, confirmed in `query_endpoint`

### What the teacher must never see:
- A silent hang past 25s with no timeout message
- A raw exception string in place of the friendly timeout copy ("Local reasoning timed out. Check Ollama, then try again.")
- An activity pack missing its source citation (every generated artifact should trace to Manuale or local material)

**Correction (LV P0 improvement cycle, 2026-07-20)**: the "(enforced)" label on the 25s timeout was overclaiming the *mechanism*, not just the number. `query_endpoint` did wrap reasoning in `asyncio.wait_for(..., timeout=timeout_seconds)`, but `ReasoningEngine._call_model` called the blocking `urllib.request.urlopen` directly inside an `async def` with no `await` point — asyncio had nowhere to deliver a cancellation. Live repro before the fix: POSTing `timeout_seconds: 1` to `/api/query` against the real dev server still took ~20.1s (`LV_REASON_TIMEOUT_SECONDS`'s own internal socket timeout), not ~1s. The default case (`timeout_seconds` unset → 25s outer budget vs. 20s inner socket timeout) happened to look correct only because the inner timeout was coincidentally shorter than the outer one, not because `wait_for` was actually enforcing anything. Fixed: the blocking call now runs via `asyncio.to_thread`, so the coroutine genuinely yields and `wait_for` can cancel it on schedule. Re-verified live: `timeout_seconds: 1` now returns the documented timeout copy in ~1.15s.

---

## P0-EXP09: Health / Doctor Check

### User does:
Clicks Health nav item, or runs `lv health` / `lv doctor` from the terminal.

### System interaction sequence:

| # | State | Copy | Response budget | Notes |
|---|---|---|---|---|
| 1 | Loading | "Running Doctor..." | — | `static/index.html:903` |
| 2 | Result header | Doctor's own summary line (one of: "Everything looks healthy." / "Something may need attention, but you can keep working." / "I found a safe fix, but I did not apply it." / "An approved update is available." / "I cannot fix this safely on my own." / "I found a privacy risk and stopped.") + status badge (OK = ok-styled, anything else = warn-styled) | — | `doctor/support_loop/doctor.py:_summary_for()`, `static/index.html:907` |
| 3 | Support bundle (if not OK) | "Create Support Bundle" button → ZIP with logs, traces, anonymized counts, no raw files uploaded | — | `src/web.py:support_bundle()` |

### Screen complement:
Single surface. Note the summary language is deliberately first-person and plain ("I found...", "I cannot fix this safely on my own.") — this is Doctor's own established voice from `doctor/support_loop/doctor.py`, not something this document is proposing.

### Response budget:
- Doctor run: **no documented timeout in the web path** — **(proposed, unverified)**. `lv health --full` (CLI) runs Doctor + pytest + gauntlet + golden eval + 5xx count, which is a multi-second-to-minute operation by nature; the web `/api/health` path is a lighter check and has no stated budget.

### What the teacher must never see:
- A green "OK" status while a real check is failing underneath (health status must be sourced from the actual check results, not a hardcoded default)
- The `PRIVATE_RISK` status rendered with the same visual weight as `WARN` — a privacy stop should read as more urgent than a routine warning, and right now both map to the same `warn` CSS class (`status.data === "OK" ? "ok" : "warn"`) — **this is a real gap worth flagging**, not a designed choice

---

## Happy State Summary Table

| P0 | Entry Point | Enforced Budget | Key Moment |
|---|---|---|---|
| EXP01 | curl/install.sh | — | No UI — terminal only |
| EXP02 | First page load | Role modal blocks paint | Local-first by default, no key required to start |
| EXP03 | Why nav / "Why?" button | — | Query hash, never raw text |
| EXP04 | Privacy nav | — | "all local" badge backed by architecture, not display logic |
| EXP05 | Profile nav | — | Full local-only summary + export + irreversible clear |
| EXP06 | Observe → mic or type → save | — | Transcript echoed back (safe to, because it never had an external path) |
| EXP07 | Parents → generate | — | Name-strip + attribution-strip before teacher sees draft |
| EXP08 | Prepare → generate | **25s timeout (confirmed in code)** | Request/response, not streamed; friendly timeout message |
| EXP09 | Health nav / `lv doctor` | — | Doctor's own first-person, plain-language status copy |

---

## What This Document Deliberately Does Not Claim

- **No formal response-time SLA exists for LV today.** Every budget marked "(proposed, unverified)" above is a suggested target, not a measured or code-enforced one. The only confirmed hard number is the 25s timeout in `query_endpoint`. Treat the rest as a starting point for a future latency-instrumentation pass, not as a spec already met.
- **LV has no voice output.** This document is not a placeholder for a future TTS layer — the STT-only mic in Observe is a convenience input method, not the seed of a broader voice surface. If LV ever gets a voice output layer, MC's `VOICE_HAPPY_STATE_P0` doc (VIU resolution, phrase cache, silence budgets) is the pattern to port, not this one.
- **LV's protection model is architectural exclusion, not runtime interception.** MC's hard-block P0s (EXP06-08 in the MC doc) catch sensitive content at an entry gate and refuse to process it. LV's equivalent (`observation_capture.py`) never builds an external-routing code path for `blocks_external` content in the first place — there's no gate to bypass because there's nowhere for it to go. Both are valid governance strategies; conflating them would misdescribe LV's actual design.

---

## Build Status Reference (fuller inventory)

The experiences above are the P0 set. LV has ~40 built experiences total; the rest (Plan, Assess, Students roster, Reflect, Quick Capture, Settings, PWA install, native launcher, coordinator Programme view) are documented but not scripted here since they don't carry a distinct trust or governance moment the way the P0s above do. Coordinator views (Evidence, Capacity, Trends) are spec'd only — they return a `deferred` status and are out of scope for a happy-state doc since there is no happy path yet.
