# Lingua Viva Demo Window Report

Date: September 3, 2026  
Repo: `/home/mical/learning-architecture`  
Branch: `main` at `9adef99`  
Demo app: `desktop-v0.2.83`, runtime `1.0.7`

## 1. Teacher Guide Created

Input guide reviewed:

- `/home/mical/Downloads/Lingua_Viva_Teacher_Guide(1).docx`

Created current guide files:

- `/home/mical/Downloads/Lingua_Viva_Teacher_Guide_Current_2026-09-03.md`
- `/home/mical/Downloads/Lingua_Viva_Teacher_Guide_Current_2026-09-03.docx`

The Markdown version is the one to edit from now.

The guide was rewritten for what is actually built today:

- current desktop build: `desktop-v0.2.83`
- runtime health version: `1.0.7`
- local-first privacy model
- roster import
- observations
- student lenses
- document-to-lens updates
- lesson preparation
- parent summaries
- Ask limitations
- Sources, Privacy, Why, Profile, Settings
- known limits for the demo build

## 2. Public Download Verification

Checked `https://linguaviva.art/`.

Confirmed the live site download buttons point to:

- Windows: `desktop-v0.2.83/LinguaViva-Setup.exe`
- Mac: `desktop-v0.2.83/LinguaViva.dmg`
- Linux AppImage: `desktop-v0.2.83/LinguaViva.AppImage`

Confirmed release assets returned HTTP `200`:

- `LinguaViva.dmg`
- `LinguaViva-Setup.exe`
- `LinguaViva.AppImage`
- `LinguaViva.deb`

Confirmed GitHub release metadata:

- tag: `desktop-v0.2.83`
- draft: `false`
- prerelease: `true`
- assets present: all four desktop artifacts

Confirmed CLI latest remains:

- `v1.0.6`

## 3. Demo Data Read-Through

Demo packet location:

- `/home/mical/learning-architecture/demo-data/`

Files present:

- `DEMO_CHEAT_SHEET.md`
- `classe-3B.csv`
- `piano_lezione_poesia_3B.txt`
- `pagella_abigail_chang.txt`
- `note_progresso_marco_luca.txt`
- `lavoro_studente_noemi.txt`
- `osservazione_giuseppe.txt`
- `osservazione_sofia_bianchi.txt`

Initial problems found:

- Cheat sheet said `Thu Sep 4, 2026`; September 4, 2026 is Friday.
- `pagella_abigail_chang.txt` named a real school.
- `piano_lezione_poesia_3B.txt` was listed as a lens-update upload, but the current lens-update classifier sees it as a class-list-like document because it mentions multiple students.
- Several student documents initially classified as `other` until given a current classifier-compatible progress-report marker.
- The Marco/Lucà progress note initially matched/extracted incorrectly, putting Marco content under Lucà and giving Marco zero fields.

Fixes made:

- Changed cheat sheet title to `Fri Sep 4, 2026`.
- Replaced the real school name with `Scuola Internazionale Demo`.
- Updated cheat sheet to use `piano_lezione_poesia_3B.txt` in **Prepare**, not Students -> lens-update.
- Added safe `Progress report` headers to the student-lens update documents.
- Reshaped `note_progresso_marco_luca.txt` into clearer, shorter separated sections so both `Chang Marco` and `Lucà Rossi` are detected and extracted separately.
- Re-copied updated demo files into `~/.lingua-viva/imports/`.

## 4. Demo Data Verification

Roster extraction:

- `classe-3B.csv` detects all 6 students.
- Accents remain intact.
- Detection confidence: `0.99` for each student.

Detected students:

- `Lucà Rossi`
- `Noëmi Villa`
- `Chang Abigail`
- `Chang Marco`
- `Bianchi Sofia`
- `Giuseppe Esposito`

Document classification and name matching:

| File | Classification | Matches |
|---|---|---|
| `lavoro_studente_noemi.txt` | `student_report` | `Noëmi Villa` |
| `note_progresso_marco_luca.txt` | `student_report` | `Chang Marco`, `Lucà Rossi` |
| `osservazione_giuseppe.txt` | `student_report` | `Giuseppe Esposito` |
| `osservazione_sofia_bianchi.txt` | `student_report` | `Bianchi Sofia` |
| `pagella_abigail_chang.txt` | `student_report` | `Chang Abigail` |
| `piano_lezione_poesia_3B.txt` | `class_list` when sent through lens-update | Use in Prepare only |

Real `lv lens-update --preview-only --json` check on the five student documents:

- preview items: `5`
- all five classified as `student_report`
- all produced reviewable fields
- Marco/Lucà file separated cleanly:
  - `Chang Marco`: 3 fields, all need review
  - `Lucà Rossi`: 4 fields, all need review

Important demo instruction:

- Use `piano_lezione_poesia_3B.txt` in **Prepare**.
- Use the five student/report/observation files in **Students -> Update lenses from documents**.

## 5. Local Source App Smoke

Started the source app once from:

```bash
cd /home/mical/learning-architecture
PYTHONPATH=. python3 -m src.web 8787
```

Confirmed:

- `/` returned HTTP `200`
- `/api/health` returned HTTP `200`
- version: `1.0.7`
- routers loaded: `5/5`

The source server was then stopped because the requested test target was the packaged desktop app, not localhost from source.

## 6. Packaged Desktop App Launch

Existing local AppImages were older (`v0.2.69` or earlier), so the current AppImage was downloaded:

- `/home/mical/Downloads/LinguaViva-desktop-v0.2.83.AppImage`

Downloaded from:

```text
https://github.com/lingua-viva/learning-architecture/releases/download/desktop-v0.2.83/LinguaViva.AppImage
```

Marked executable:

```bash
chmod +x /home/mical/Downloads/LinguaViva-desktop-v0.2.83.AppImage
```

Normal launch failed on this Linux machine because of the standard AppImage/Electron SUID sandbox issue:

```text
The SUID sandbox helper binary was found, but is not configured correctly.
```

Launched successfully with:

```bash
/home/mical/Downloads/LinguaViva-desktop-v0.2.83.AppImage --no-sandbox
```

Confirmed the running backend is from the packaged AppImage, not the source checkout:

```text
/tmp/.mount_LinguaAnp323/resources/app/src/web.py 8787
```

Packaged app health:

- status: `OK`
- version: `1.0.7`
- routers loaded: `5/5`
- privacy path scan: pass

## 7. Current Test Status

Current packaged desktop app is running.

Use the desktop window for the demo test.

The app backend is available at:

```text
http://127.0.0.1:8787
```

That backend is currently served by the packaged AppImage, not by the repo source server.

## 8. Remaining Demo Notes

- Keep Ollama running.
- `ollama list` confirmed `qwen3:8b` is available.
- The full six-document lens-update run is too slow for a live cold demo; use the five student documents selectively.
- Avoid presenting the lesson-plan file as a student-lens update document.
- Use typed observations if voice STT is unreliable.
- Treat generated lesson materials as drafts and review Italian/source alignment before presenting them as usable output.
- Do not promise Google Drive or Slack are plug-and-play unless the machine is already configured.

## 9. Files Changed In This Window

Created:

- `/home/mical/Downloads/Lingua_Viva_Teacher_Guide_Current_2026-09-03.md`
- `/home/mical/Downloads/Lingua_Viva_Teacher_Guide_Current_2026-09-03.docx`
- `/home/mical/Downloads/LinguaViva-desktop-v0.2.83.AppImage`
- `/home/mical/learning-architecture/demo-data/DEMO_WINDOW_REPORT_2026-09-03.md`

Edited under `demo-data/`:

- `DEMO_CHEAT_SHEET.md`
- `pagella_abigail_chang.txt`
- `piano_lezione_poesia_3B.txt`
- `lavoro_studente_noemi.txt`
- `osservazione_giuseppe.txt`
- `osservazione_sofia_bianchi.txt`
- `note_progresso_marco_luca.txt`

Copied updated demo files to:

- `~/.lingua-viva/imports/`

No app source code was changed in this window after the prior consolidation commit.
