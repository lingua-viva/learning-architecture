# BASELINE — U1 install & first run (Rung 1, nothing fixed)

**Date:** 2026-09-04 (afternoon, PC-23) · **Prompt:** `dev/PROMPT_LV_U1_INSTALL_TO_GREEN_2026-09-04.md` · **Branch:** `ux/u1-install` off `main` `30f5e03`
**Seat:** PC-23 (Windows 11, this is NOT a clean box — a developer laptop). **The clean-Windows and clean-Mac installs of prompt §3.2 cannot be performed from here; they are CANNOT-TELL on this box and are Mical's live cycle.**

## 1. The live download (prompt §3.1) — measured, not quoted

```
site pin        https://linguaviva.art/ -> desktop-v0.2.84            (curl, 2026-09-04)
release         desktop-v0.2.84 · published 2026-09-03T19:17:01Z · prerelease: True
assets (HTTP)   LinguaViva-Setup.exe 302 (81 MB) · LinguaViva.dmg 302 (111 MB) · LinguaViva.AppImage 302 (110 MB) · LinguaViva.deb (77 MB)
contains        main up to 71b069d (Italian safeguarding fix) — NOT the 29 commits pushed today (cycle 0, run 33908229547 in flight)
```

## 2. Error register — what this box can establish

| # | path | finding | class | status |
|---|---|---|---|---|
| E1 | Doctor / `/api/health` on Windows | four `subprocess.run(["python3", …])` sites crashed Doctor and left health "degraded" on every Windows box | hardcoded interpreter | **fixed on main since cycle 0** (`3eaa943` → `sys.executable`); not yet in any download |
| E2 | Doctor in a packaged (no `.git`) tree | run against a `git archive` copy with no `.git`: **status WARN**, three warns are "not a git repository" — but `check_branch` has an explicit `_desktop_mode()` branch that turns these into PASS in a packaged build (`doctor/support_loop/doctor.py:154-158`). This copy is not desktop mode, so the WARN is the dev-tree shape, not the teacher's | CANNOT-TELL until run inside the packaged app; **Mical's Doctor click is the measurement** | open |
| E3 | Doctor privacy scan | the scan names `resume-cv\Claudia_CanuFautre_Resume.docx` — a real person's résumé present in the working tree | personal data in the tree | see §4 — checked whether tracked/packaged |
| E4 | desktop bootstrap interpreter search | `desktop/electron/bootstrap.ts:125-126`: Windows tries `["python","python3","py"]`, POSIX `["python3","python"]` — correct order per platform | — | no defect found by reading |
| E5 | `install.sh:204` | the curl installer starts the server with `python3` — POSIX-only path, correct there | — | none |
| E6 | POSIX file-mode `os.chmod(path, 0o600)` — 21 sites | no-ops on NTFS; 7 tests assert the mode and fail on Windows (baseline 34) | test class, not product | none for a teacher |
| E7 | four install tests (`test_install_hardening` ×3, `test_install_launcher_scripts`) | `WinError 2`: they execute bash install/launcher scripts, which do not exist as processes on Windows | test environment | none for a teacher |

**Olga's 2026-09-03 errors are not reproduced here** — she was on her own machine, the errors were not captured (*"another error popped up but I accidentally closed it"*), and this box is not clean. That is the honest state of E-Olga: CANNOT-TELL, and it is the reason §3 exists.

## 3. What closes U1's Rung 1 — Mical's live cycle on v0.2.85

The click path from prompt §6, run on the live download the moment cycle 0's release lands:

```
1. Click the download button on https://linguaviva.art/ (not a direct asset URL). Note the tag it serves.
2. Open the installer. Note every dialog verbatim.
3. First launch. Start a timer. Minute one: what is on screen?
4. Governance → Doctor. Expected: green, in plain words. If WARN/BLOCKED: copy the check names verbatim (E2 above is the question).
5. Students → import demo-data/classe-3B.csv → approve → confirm. Expected: 6 lenses exist (Lucà, Noëmi with accents).
6. Quit. Relaunch. Expected: the 6 students are still there.
7. Disconnect network. Relaunch. Expected: works, or names exactly what is unavailable.
Log each step PASS / FAIL / CANNOT-TELL with the exact wording seen -> dev/WITNESS_LOG_UX_2026-09.md
```

## 4. E3 — the résumé: tracked, not shipped

`resume-cv/Claudia_CanuFautre_Resume.{docx,md}` are tracked (committed by Claudia herself, 2026-04-19, `4840a06` — it is her own tool's repo). The desktop bundle uses an explicit **include** list (`desktop/package.json` `extraResources`: `src/**`, `ontology/{core,domains,education,proposals}/**`, `lenses/{core,professional,education}/**`, `knowledge/**`, `memory/**` minus data, …). `resume-cv/` is not on it, and neither is `lenses/LENS-PERSON-002_claudia_canu.yaml`. **Not shipped to any installer.** No U1 action. Whether personal files belong in a repo that nine schools' builds are cut from is the operator's question, not a build item.

## 5. Kill criteria status (prompt §2)

K1–K3 not evaluable until Rung 2; K4 not triggered (no workflow edits); K5 awaits the witness.
