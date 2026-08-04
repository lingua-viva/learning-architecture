# REVIEWER VERDICT — c5a27ef (2026-08-04)

**Reviewer:** Claude Code, build machine
**Commit reviewed:** `c5a27ef` on `main` (not pushed to origin)
**Verdict: NO-GO.** Do not push. Two of six requested checks fail outright; a
third (A5/T7) was already known-absent. Per the worklist's own rule ("GATE A —
block release until ALL green"), this alone is disqualifying independent of
the other findings.

---

## 1. Full pytest (A6) — FAIL

`pytest -q tests/` → **8 failed, 1965 passed, 13 skipped** (1227s / 20m27s).
Not the "known risk" Kiro flagged (`/api/voice/act`) — three distinct root
causes, none of them that one:

### 1a. Route-reachability manifest gap (4 failures, mechanical fix)
`B4` added `/api/sync/status` but never classified it in the reachability
manifest. Breaks:
- `test_route_reachability.py::test_route_reachability_check_passes_against_the_real_repo`
- `test_route_reachability.py::test_every_live_route_is_classified_exactly_once`
- `test_lv_preflight.py::test_preflight_passes_on_clean_tree` (cascades from the same script)
- `test_lv_preflight.py::test_preflight_json_reports_all_six_checks` (same)

Fix: add `GET /api/sync/status` to the manifest's `reachable_from_ui` or
`intentionally_backend_only` list (whichever is accurate — it's called from
Settings, so probably `reachable_from_ui`). One-line data fix, low risk.

### 1b. TTS locale tests pinned to removed literal (3 failures, test debt not behavior bug)
`B2` replaced `speakLocally()`'s unconditional `utterance.lang = "it-IT"`
with the `looksEnglish` ternary. Behavior is still correct — verified live
(§2 below) that Italian content still resolves to `it-IT`. But three tests
string-match the literal that no longer exists in that exact form:
- `test_voice_recognition_language.py::test_playback_speaks_italian_not_english`
- `test_voice_recognition_language.py::test_playback_sets_language_before_reading_the_voice_list`
- `test_voice_tts_privacy_gate.py::test_local_fallback_still_speaks_italian`

These need updating to assert on the new dynamic-detection shape (e.g. assert
the ternary exists and resolves correctly for known Italian input), not
reverted. Behavior is fine; the tests are stale.

### 1c. A4/BUG-5 test conflict (1 failure — same root cause as §2)
`test_oka_voice_hardening.py::test_observe_requires_human_review_before_save`
pins the OLD forced-type UI copy (`"Choose a type (required)"`,
`if (!templateType)` gate) from the 2026-08-02 BUG-5 fix. A4 removed that
gate from the frontend but this locked test was never reconciled — and
critically, per §2, the *backend* guard this test's spirit protects is still
active. This is not two bugs, it's one unfinished migration.

---

## 2. A4 (save with only text + student) — **FAIL, confirmed live**

Kiro's report claims DONE. It is not, end-to-end:

- **Frontend** (`static/index.html` `saveObservation()`): correctly relaxed —
  no client-side block on empty type/CEFR/level. Confirmed by reading.
- **Backend** (`src/web.py:3738-3743`, `/api/observe/capture`): still hard-
  rejects empty `template_type` with `400 {"error": "Choose an observation
  type before saving. Nothing was saved."}` — this guard was added for
  BUG-5 (2026-08-02, to stop the server from *inventing* cefr/speaking/A1
  when fields were omitted) and was never updated for A4.

**Live repro** (ran against `c5a27ef` via `TestClient`, not simulated):
```
POST /api/observe/capture {"student_id": "any", "transcript": "text only, no type"}
→ 400 {"error": "Choose an observation type before saving. Nothing was saved."}
```

So today, a teacher who leaves "Observation type" at its default ("Not
tagged") and saves text-only gets a **rejected save**, not a successful one.
This is worse for Claudia's actual complaint (P1-2: forced arbitrary picks →
invented data) only in that it no longer *invents* data — but it still
blocks the save entirely, which the worklist's own DONE-PROOF explicitly
rules out ("an observation with text + student only saves").

No new regression test was added for A4 despite the closure report claiming
one was (`grep` across `tests/` for anything A4-specific returns nothing new
in this diff).

**This needs a product decision, not a quick patch**: does an untyped
observation get stored as `template_type: null`/`"general"` (requires a
schema decision — does the lens/cohort-tier code handle a null type
gracefully downstream?), or does the UI need to re-force a neutral default
that isn't a false clinical claim? Recommend this goes back to whoever ruled
the original A4 spec before Kiro re-touches it, per the postmortem's own
"lane reassignments get one written line before they take effect" discipline
— this is closer to a reassignment than a bugfix.

---

## 3. B2 (English refusal → English voice) — PASS (code-level)

`speakLocally()`'s `looksEnglish` regex tested via `node` against the actual
`ask_personal_data_refusal_message()` string: matches, resolves to
`utterance.lang = "en"`, filters to `/^en/` voices. Correct. Could not test
actual audio output — no browser/speaker in this environment; live listening
check still needed by a human.

---

## 4. T5 (Observe mic) — PASS (code-level only), zero test coverage

Wiring matches Kiro's report exactly: `obs-mic` → `captureLocalStt` →
`onTranscript` appends to `#obs-text` (accumulate, not replace); form-gated
save (no bypass); `applySttAvailability()` correctly dims/disables `obs-mic`
when STT is unavailable. Could not physically test — no mic/desktop app in
this shell. **Zero automated tests exist for this path** (searched
`tests/` for `obs-mic`/`captureLocalStt`: no hits). Recommend the operator
do the literal tap-mic-dictate-edit-save pass at the desktop app before this
ships, since it's genuinely unverified beyond static wiring.

---

## 5. A5 (T7 e2e gate) — confirmed NOT DONE (already known)

No `scripts/run_docpipe_e2e.sh`, no `lv eval docpipe` command anywhere in
`src/`. Only the undispatched spec `dev/PROMPT_PAIR_T7_E2E_AUDIT_2026-08-04.md`
exists. `dev/AUDIT_KIRO_BUILD_2026-08-04.md` also still doesn't exist. Matches
Kiro's own report — flagging again because the worklist's Gate A rule is
"block release until ALL green," full stop, independent of severity.

---

## Recommendation

**Do not push c5a27ef.** Three items need to close before this is a real
Gate A:

1. Fix the route-reachability manifest gap (§1a) — mechanical, low risk.
2. Decide A4's actual data-model answer and reconcile frontend + backend +
   the BUG-5-era locked test (§2, §1c) — needs a ruling, not just code.
3. Either fix the TTS test literals (§1b) or explicitly accept them as
   updated-not-reverted — low risk but still required for "full green."

A5/T7 (§5) and live T5/B2 checks (§3, §4) are open risk the operator may
choose to accept for a fast-follow, per the worklist's own Gate A/B
distinction — but that's an explicit call to make out loud, not a default.

Full pytest raw output was 1227s under load average ~18 on a 16-core box
(concurrent mission-canvas suite running in parallel) — re-run in isolation
if timing-sensitive tests are ever added here.
