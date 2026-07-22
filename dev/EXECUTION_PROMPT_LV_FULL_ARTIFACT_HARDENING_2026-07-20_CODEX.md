# Prompt: LV Full Artifact Hardening (Codex)

Copy everything below the line into a fresh Codex session, run from the repo
root (`learning-architecture`). Codex has shell + file access. Network access
is needed for `https://linguaviva.art` and GitHub release verification; local
app verification uses `localhost:8787`.

---

You are running as Codex inside the `learning-architecture` repo. This is a
full artifact hardening pass for Lingua Viva. Treat it as an implementation
and verification task, not a proposal. Produce the report file and make fixes
where defects are clear. Leave everything uncommitted.

## Required Reading

Read these in order before making changes:

1. `CLAUDE.md`
2. `dev/INDEX.md`
3. `dev/specs/SPEC_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`
4. `dev/specs/SPEC_DOWNLOAD_BUTTONS_2026-07-20.md`
5. `dev/specs/SPEC_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md`
6. `dev/reports/REPORT_INSTALL_RELEASE_PIPELINE_HARDENING_2026-07-20.md`
7. `dev/specs/SPEC_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`
8. `dev/reports/REPORT_LV_P0_IMPROVEMENT_CYCLE_2026-07-20.md`
9. `dev/reports/REPORT_LV_CLAUDIA_LENS_HARDENING_2026-07-20.md`

Then inspect the actual surfaces:

- `static/index.html`
- `src/web.py`
- `src/pwa.py`
- `static/sw.js`
- `static/offline.html`
- `install.sh`
- `install.ps1`
- `.github/workflows/release.yml`
- `.github/workflows/install-test.yml`
- `desktop/package.json`
- `desktop/electron/main.ts`
- `doctor/`

## Hard Rules

- No real student data, institution names, colleague names, or private school
  documents in any report, test, fixture, screenshot, log, or support bundle.
- Do not modify Tier 1 governance.
- Do not change LV's protection model from architectural exclusion to runtime
  interception.
- Do not commit.
- If you edit `static/index.html` or `src/web.py`, run
  `python3 scripts/check_ui_contract.py --bump` and then verify it.
- Use `python3 -m pytest -q tests/` for the full suite.
- Do not claim `linguaviva.art` or latest GitHub release status from memory.
  Verify live.
- If an issue requires DNS, release tagging, GitHub publishing, signing, or
  other operator credentials, mark it `ESCALATED` with the exact action needed.

## Task

Harden every individual artifact and user-facing use case that exists today:

- public site and download buttons on `linguaviva.art`
- GitHub release assets and workflow promises
- macOS/Linux/Windows install scripts
- desktop app packaging contract
- first-run/onboarding/Ollama/model-provider experience
- app shell/sidebar/PWA/offline/share behavior
- all teacher experiences: Home, Plan, Prepare, Observe/microphone notes,
  Students/student lenses, Assess, Ask, Parents, Why, Privacy, Profile/export/
  clear, Provider Settings, File Map, Reflect, Quick Capture, Health/Doctor,
  support bundle
- coordinator/admin views: Programme, Evidence, Capacity, Trends
- backend route contracts and privacy/data artifacts supporting those flows
- docs/spec/report status truth in `dev/INDEX.md`

For each artifact:

1. Inventory the real entry point from source and the running app.
2. Live-run it as a user would.
3. Record actual response/copy/error/recovery behavior.
4. Fix concrete defects.
5. Add or update regression coverage where appropriate.
6. Re-run the live path.
7. Mark it `PASS`, `FIXED`, `DEFERRED`, or `ESCALATED`.

Do not under-deliver. The deliverable is a real file:

`dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md`

If you find yourself writing more than a few paragraphs in chat without
touching code or the report, stop and work in the files.

## Required Live Runs

Start the app:

```bash
python3 -m src.lv_cli serve 8787
```

In another shell, verify:

```bash
curl -fsS http://127.0.0.1:8787/api/health
curl -fsS http://127.0.0.1:8787/ | head
```

Walk the app in a browser or browser automation. Do not verdict from source
alone. Use direct API calls only as supporting evidence.

Verify public distribution:

```bash
curl -I https://linguaviva.art
curl -fsSL https://linguaviva.art | head
gh api repos/lingua-viva/learning-architecture/releases/latest
```

For every visible download button, confirm the target URL and status. If a
button is intentionally disabled, confirm the visible copy is honest.

## Minimum Verification Before Final

Run and record:

```bash
python3 -m pytest -q tests/
python3 -m src.lv_cli preflight
python3 scripts/check_ui_contract.py
python3 -m py_compile src/web.py src/lv_cli.py src/pwa.py
sh -n install.sh
```

If PowerShell is available, also run a syntax or no-op validation for
`install.ps1`. If it is not available, state that limitation.

## Report Format

Write `dev/reports/REPORT_LV_FULL_ARTIFACT_HARDENING_2026-07-20.md` with:

1. Findings first, ordered by severity and impact, with file/line references.
2. Full artifact inventory table:
   `Artifact | Entry point | Status | Evidence | Fix shipped or next action`
3. Public site/download verification table:
   `URL/button | Expected | Actual | Status | Evidence`
4. Onboarding/Ollama verification table.
5. Per-experience table for every teacher and coordinator/admin view.
6. Backend/privacy/support artifact table.
7. Changes shipped, with file references.
8. Factual corrections to prior specs/reports, if any.
9. Final verification commands and results.
10. Operator-only follow-ups, if any.

Finally update `dev/INDEX.md` for this spec with the real outcome and report
link, matching the existing table format.

Final chat response under 150 words: report path, top 3 punch-list items, and
test result. Nothing else.
