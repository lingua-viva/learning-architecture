# UX TRACKER — Lingua Viva: every UX meant to be working, and what is actually proven

**Living file.** One row per UX. Update the row in the same commit that changes its truth. Levels are the readiness path's (`dev/PATH_TO_UX_READINESS_2026-09-04.md`): **0** not built · **1** backend only · **2** UI-reachable · **3** end to end on a fixture, inspected · **4** witnessed by the intended user on the live download · **5** unattended a week. A level is claimed only with a source: a test file, a witness-log row, or a builder record. "Verified journey" (`dev/OVERNIGHT_VERIFIED_JOURNEYS_2026-09-05.md`) means level 3 on synthetic data by an agent, never 4.

**Live build:** `desktop-v0.2.95` (2026-09-05 06:19Z; tag commit `eaa5ed4`; site pinned; three installers 302). **Last human on a live build:** Claudia, PC-23 Windows, 2026-09-05 03:00–03:10Z on v0.2.91 (U2 PASS, U3 FAIL → fixed in v0.2.92, redo not done). **Mac build:** never run by a human — Chip's run is scheduled (`dev/PROMPT_CHIP_LV_RETEST_2026-09-05.md`).

| # | UX | level | proven by | last human (who · when · tag · verdict) | what moves it | owner / next |
|---|---|---|---|---|---|---|
| U1 | Install & first run | **2** | `test_desktop_ollama_spawn.py` (ENOENT class), `test_c8_install_over_install.py`, window-bounds clamp (v0.2.93+), Mac signed team XWT7RB624U | PC-23 seat · 09-05 · v0.2.90 → **FAIL** (spawn ollama ENOENT) → fixed v0.2.91; Olga · 09-03 · older · FAIL (errors, one lost) | a clean Windows and a clean Mac run with every dialog recorded | Chip checks 1–3 (Mac); Olga re-install |
| U2 | Roster → lenses | **4** | `test_u2_roster_honesty.py` (6) | **Claudia · 09-05 03:06Z · v0.2.91 · PASS** (6 lenses, accents, grade 3B) | keep it; file-picker friction noted (copies in Documents / Downloads) | Chip checks 4–5 (Mac) |
| U3 | Any document about a student → lens | **3** | `test_u3_review_confirm.py` (4), `test_cefr_italian_labels.py` (4), corpus tests in `tests/fixtures/docpipe/`; originals + revisions retained (v0.2.93), PDF/Word decoded evidence, restricted route for family reports (builder) | Claudia · 09-05 03:08Z · v0.2.91 · **FAIL** (Italian CEFR labels unknown; held fields invisible) — fixed in v0.2.92, **redo not done** | Claudia's pagella redo; a second document type; the corpus of expected types (other-school report card, progress report, IEP, family report, letter, scan, photo) | Claudia; Chip checks 6–7 |
| U4 | Observe → the right section | **3** | `test_observe_to_lens.py` (8), `test_u8_editable_lens.py`; original recordings retained and reopened from Sources (v0.2.95) | none on a live build | Italian routing vocabulary audit; voice note by Olga | Chip check 12 |
| U5 | Assess: oral / text → diagnostic → lens | **3** | builder journeys: text, English + Italian synthetic speech, in-app recording → correction → four findings → confirm → lens → Sources → undo; Whisper `small` WER 0.000 EN / 0.065 IT on synthetic speech | none; **promised to Olga within two weeks of 09-03** | a real voice (Chip), then a child's voice with Olga; the S1 storage-shape ruling is recorded as "append-only records, assessment_profile a projection" | Chip checks 8–9, 11; Olga |
| U6 | Assess: written work / photo | **3** | builder: rapidocr local OCR, typeset Italian photo + scanned PDF, mandatory correction step | none | real handwriting (Chip check 10), then a student's page with a teacher | Chip check 10 |
| U7 | View a lens | **2** | provenance on the wire (`source_ref_ids`), `test_u13` proves RED absent | Claudia · 09-05 · v0.2.91 · looked at Abigail (one entry; held fields invisible — fixed) | provenance rendered per entry; "what changed" strip; a teacher narrates the page | Claudia after the redo |
| U8 | Edit a lens by hand | **3** | `test_u8_editable_lens.py` (6 incl. sticky remove) | none on a live build | edit text in place; move bucket; undo a remove | Chip check 9 (remove/undo) |
| U9 | Prepare: differentiated materials / packet | **3** | builder: uploaded water-cycle lesson → three tiers with the upload's terms → printable packet → saved → reopened in Sources (real local model) | none | tiers must say whether a model was used; Italian output for an Italian lesson; a teacher reads the tiers | Chip check 14; Claudia |
| U10 | Summaries: parent note | **3** | `test_u10_approve_print.py` (8): evidence gate, approve, print, name tokens; approved revisions immutable and reopened (v0.2.94) | none on a live build | tone spec (`SPEC_PARENT_NOTE_TONE`); Italian notes; one real note sent | Chip check 15; Claudia |
| U11 | Ask | **2** | cold-start refusal not built; BUG-5 (fabrication) open | Claudia · 08-29 · FAIL (fabricated claims) | minimum-evidence refusal; citation check against the lens | next lane |
| U12 | Sources / saved work / file map | **3** | builder: saved parent notes, packets, diagnostics, admin answers reopen / download / print; originals under `~/.lingua-viva/vault/sources`, runs under `imports/`, saved work under `deliverables/saved` | none | a teacher finds yesterday's work in Sources without help | Chip (every Sources step) |
| U13 | Safeguarding / Governance / Health | **3** | `test_u13_safeguarding_through_the_routes.py` (15): RED rows through the typed route, absent from every surface, pending count, coordinator panel; document route restricted (builder, EN + IT family reports) | none on a live build (Claudia's 08-29 sentence was the origin) | Claudia types the sentence in her app (spec R4); a native-speaker review of the Italian indicators; a notification channel without Slack (ruling) | Chip check 13; Claudia |
| U14 | Profile / Settings | **3** | `test_sir_profile.py` (8): School profile select + Apply (v0.2.90), teacher identity | none | provider connect/disconnect on a clean machine; Whisper size setting | Chip (Settings during check 3) |
| U15 | Home / Daily / Plan | hidden | removed from both profiles' navigation (v0.2.94, operator ruling); code kept | Olga · 09-03 · ruled them out | Plan returns only when its research/material workflow works | — |
| U16 | Slack | hidden | out of scope (operator ruling 09-05) | — | — | — |
| U17 | Reflect | **2** | exists; not witnessed | none | witness | later |
| U18 | Admin: query across lenses | **3** | `test_lens_query.py` (11); **Lens queries** view on `adminNav`, Run and save answer, CSV, saved in Sources (v0.2.94) | none | a coordinator runs one question and reads the ARON codes in words | Chip check 16; Mical |
| U19 | Admin: teacher lenses | **1** | code exists, unreached | none | build the flow after a provisioning ruling | later |
| U20 | Admin: onboard a teacher | **0** | not built | none | ruling on the provisioning channel | later |
| C8 | Durability across updates | **4 (Windows)** | `test_c8_install_over_install.py` (8); live: v0.2.91 → v0.2.92 → v0.2.95 on PC-23 kept six lenses, levels, notes | PC-23 seat · 09-05 · v0.2.95 · PASS (a seat, not a teacher — counts as live evidence, not a teacher witness) | the same on a Mac; a backup/restore control in Settings | Chip check 17 |
| SIR | Still I Rise profile | **3** | `test_sir_profile.py`; Settings control; site section | none (Olga asked for it 09-03) | Olga sees her nav | Olga |

## Honest totals (2026-09-05 07:30Z)
- Level 4 by a teacher: **1** (U2). Level 4 by a seat, live: C8 on Windows.
- Level 3: U3, U4, U5, U6, U8, U9, U10, U12, U13, U14, U18, SIR — twelve, none yet touched by a human on a live build.
- Below 3: U1 (2), U7 (2), U11 (2), U17 (2), U19 (1), U20 (0).
- Open teacher rows: Claudia's pagella redo (U3), Olga's install and oral exam (U1, U5), Chip's Mac run (18 checks).

## How a row moves
1. A change lands with a red-first test → the *proven by* column names the file; level ≤ 3.
2. A person does the click path on a live download → `dev/WITNESS_LOG_UX_2026-09.md` gets the row with the wording; if PASS by the intended user, level 4 here, same commit.
3. A FAIL by a person is the most valuable row in this file: it names the next fix. Record it before fixing it.
4. Nothing moves on an automated pass, a screenshot by an agent, or "should work".

## Where the evidence lives
`dev/WITNESS_LOG_UX_2026-09.md` (verbatim rows) · `dev/HARNESS_LIVE_TEST_2026-09-04.md` and the harness pages (Claudia/Mical: `artifact/4acfefa3…`; Chip: `artifact/2d6787bd…`) · `dev/OVERNIGHT_VERIFIED_JOURNEYS_2026-09-05.md` and `dev/OVERNIGHT_BUILD_2026-09-05.md` (builder evidence, synthetic) · `dev/PROMPT_LV_FULL_SWEEP_2026-09-05.md` (the bar and the build per UX) · `dev/PATH_TO_UX_READINESS_2026-09-04.md` (the levels and the five properties).
