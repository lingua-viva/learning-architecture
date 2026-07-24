# Execution Prompt: LV-BLT-007 — System Stats Mount

Instance of `dev/EXECUTION_PROMPT_TEMPLATE_MOUNT_FIX_2026-07-23.md` for
`SPEC_LV_BLT007_SYSTEM_STATS_MOUNT_2026-07-23.md`. Copy the block below into a fresh session.
Working directory: `~/learning-architecture`.

---

```markdown
You're working in the Lingua Viva repo (~/learning-architecture), fixing one specific
built-but-not-mounted backend capability: LV-BLT-007 (system stats panel, /api/stats has zero
UI consumers).

This work exists because of a real, traced pattern, not a hypothetical one: 9 backend
capabilities in this repo were built, tested, sometimes hardened across 15 rounds — and never
once exercised through the actual app a teacher uses. dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md
traced this to 4 specific commit-level causes, including one that happened again in the very
same session that had just finished analyzing the problem. Read it before touching any code —
it explains why "the tests pass" is not the bar for this task.

The product bar for this task, singular: a teacher or coordinator can open the actual running
app, click Health in the nav, and see real system-scale numbers — not "the route returns 200
when curled."

## Execution Contract

1. Read the required files, in order.
2. Read dev/specs/SPEC_LV_BLT007_SYSTEM_STATS_MOUNT_2026-07-23.md in full. Build exactly its
   scope — a System panel added to renderHealth(), nothing wider.
3. Build it.
4. Verify it twice, report which kind you did:
   - Correctness-verified: /api/stats returns the right data when called directly.
   - Reachability-verified: you opened the actual served app (python3 -m src.lv_cli serve 8787,
     real browser) and clicked the Health nav item, saw the System panel render with real
     numbers. This spec is not done on correctness-verification alone.
5. Run the full verification checklist.
6. Update dev/INDEX.md, referencing this as closing LV-BLT-007.
7. Give the final response under 150 words.

## Required Reading (in order)

1. CLAUDE.md
2. dev/INDEX.md — check for other concurrent mount-fix lanes before assuming a clean
   static/index.html
3. dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md — full read
4. dev/specs/SPEC_LV_BLT007_SYSTEM_STATS_MOUNT_2026-07-23.md — YOUR SPEC
5. src/web.py:1367-1385 (/api/stats, already correct, do not modify)
6. static/index.html — renderHealth() (~line 1334) and renderPrivacy() (~line 1373) — match
   renderPrivacy()'s existing stat-card grid pattern and try/catch error handling exactly,
   don't invent a new visual style

## Hard Rules

- Build exactly what the spec scopes — the System panel in Health, nothing else. If you notice
  another BLT finding, note it in your report, don't fix it here.
- static/index.html and src/web.py are shared files other concurrent lanes may be touching —
  check git diff before assuming a clean slate; don't revert what looks unfamiliar.
- State the exact new UI call site (file:line) in your report.
- Do not claim "reachability-verified" unless you actually opened the served app and clicked
  Health. If you only curled /api/stats, say so explicitly.
- Do not commit — leave staged for operator.

## Verification Before Closing

python3 -m pytest -q tests/
python3 scripts/check_ui_contract.py --bump
python3 -m src.lv_cli serve 8787   # then reachability-verify live

## Final Response

Under 150 words: what was built + exact UI call site (file:line), correctness- vs
reachability-verified labeled explicitly, test result, anything noticed but not fixed.
```
