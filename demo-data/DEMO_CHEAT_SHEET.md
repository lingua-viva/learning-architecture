# LV Demo Cheat Sheet — Fri Sep 4, 2026

## Pre-demo: make sure

- [ ] App running: `cd ~/learning-architecture && python3 -m src.web` → opens at `localhost:8787`
- [ ] Ollama running with a model (qwen3:8b or similar): `ollama list`
- [ ] Fresh state: no students in roster yet (clean `~/.lingua-viva/runtime/student_lenses.db`)

## Demo beats (order)

### 1. Import roster (2 min)
- **Students** tab → upload `demo-data/classe-3B.csv`
- Show: 6 students detected, accented names (Lucà, Noëmi) preserved, siblings (Chang ×2) separate
- Talking point: "Everything stays on the teacher's machine. No cloud."

### 2. Upload a lesson plan in Prepare (3 min)
- **Prepare** tab → choose/upload `piano_lezione_poesia_3B.txt`
- Show: the app recognizes this as the source for lesson planning; review the selected-source line before generating
- Talking point: "Lesson materials are drafts. The teacher checks Italian and source alignment before using them."

### 3. Upload a report card (3 min)
- Upload `pagella_abigail_chang.txt`
- Show: Abigail's CEFR levels and profile fields extracted with confidence badges
- Talking point: "Teacher reviews and confirms before anything enters the student's profile"

### 4. Upload progress notes (2 min)
- Upload `note_progresso_marco_luca.txt` — mentions TWO students in one file
- Show: each student gets ONLY their section (no cross-contamination)

### 5. Voice observation (2 min)
- **Observe** tab → type or speak: "Giuseppe oggi ha usato vocabolario avanzato nella scrittura persuasiva"
- Show: matches to Giuseppe Esposito, observation attached to his lens
- If ambiguous (say "Chang was great") → show the disambiguation prompt

### 6. Review a student lens (3 min)
- Click **Lucà Rossi** → show his profile building from imported data
- Show: imported fields have yellow "needs confirmation" badges
- Confirm a few → they turn green
- Talking point: "The teacher is always the author. The app organizes, never decides."

### 7. Parent summary (2 min)
- **Student Summary** tab → pick a student with data → **"Draft Summary"**
- Show: summary only references confirmed data, no fabrication
- 3-checkbox review before copy/print

## Files on disk (ready to upload)

| File | What it shows |
|---|---|
| `classe-3B.csv` | 6-student roster with accents, siblings, mixed name order |
| `piano_lezione_poesia_3B.txt` | Lesson plan source for Prepare; do not use this one for lens-update |
| `pagella_abigail_chang.txt` | Full report card with CEFR, ATL, subjects |
| `note_progresso_marco_luca.txt` | Progress notes for 2 students in one file |
| `lavoro_studente_noemi.txt` | Student work sample with CEFR estimates |
| `osservazione_giuseppe.txt` | Observation with strategies tried |
| `osservazione_sofia_bianchi.txt` | Observation with social skills notes |

## Gotchas to avoid

- **Don't ask aggregate questions** — this is per-student, not fleet analytics
- **Voice STT may not work** — type observations as fallback (known limitation)
- **No CEFR invention** — if the app shows a CEFR level without source, that's a bug. Flag it.
- **Local models** — if classify/reason is slow, that's CPU-class Ollama. Normal.
