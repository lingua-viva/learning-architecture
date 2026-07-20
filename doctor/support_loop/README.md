# Lingua Viva Local Support Loop

Local teacher/operator support commands for Lingua Viva validation and support packaging.

Run from the Lingua Viva package or repo root:

```bash
python3 -m doctor.support_loop doctor
python3 -m src.lingua_viva.cli doctor --json
```

Teacher mode constraints:

- no `.docx` edits
- no curriculum matrix promotion
- no destructive git commands
- no unredacted support bundles
- no student-data export
- no support bundle, repair, update, or incident workflow in Phase A

Runtime state is written under `.lv_support/`, which is ignored by git.
