# Execution Prompt Template: Mount-Fix Specs (LV-BLT series)

Reusable template for every spec fixing a `LV-BLT-XXX` finding from the
`AUDIT: Built But Not UI-Mounted` / `ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` series. Fill in
`{SPEC_PATH}`, `{SPEC_ID}`, `{AGENT}` and paste the result into a fresh session. Do not skip the
required reading — it's short, and it's the whole point of this series existing.

---

```markdown
You're working in the Lingua Viva repo (`~/learning-architecture`), fixing one specific
built-but-not-mounted backend capability: {SPEC_ID}.

This work exists because of a real, traced pattern, not a hypothetical one: 9 backend
capabilities in this repo were built, tested, sometimes hardened across 15 rounds — and never
once exercised through the actual app a teacher uses. `dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md`
traced this to 4 specific commit-level causes, including one that happened again in the very
same session that had just finished analyzing the problem. Read it before touching any code —
it explains why "the tests pass" is not the bar for this task.

The product bar for this task, singular: a teacher (or coordinator, if admin-scoped) can open the
actual running app, click something real, and see this capability work — not "the route returns
200 when curled."

## Execution Contract

1. Read the required files, in order.
2. Read `dev/specs/{SPEC_PATH}` in full. This is your spec — build exactly its scope, nothing
   wider.
3. Build it.
4. Verify it **twice, and report which kind you did for each claim** (this distinction is the
   entire point — see §6.3 of the root-cause doc):
   - **Correctness-verified**: the route/function returns the right data when called directly
     (curl, a unit test, a Python REPL call).
   - **Reachability-verified**: you opened the actual served app (dev server minimum — run
     `python3 -m src.lv_cli serve 8787` or equivalent and hit it with a real browser, or the
     installed desktop app if available) and triggered the feature the way a teacher would —
     clicked the nav item, clicked the button, saw the real result render.
   A spec is not done on correctness-verification alone. If you cannot reachability-verify (no
   browser available, headless environment), say so explicitly in your report — do not claim it
   anyway.
5. Run the full verification checklist.
6. Update `dev/INDEX.md` with this spec's status, referencing which BLT finding it closes.
7. Give the final response under 150 words.

## Required Reading (in order)

1. `CLAUDE.md` — repo architecture, privacy rules
2. `dev/INDEX.md` — current spec status (other mount-fix lanes may be running concurrently —
   check for file overlap before assuming a clean slate)
3. `dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md` — full read, not skimmed. §3 explains which
   of the 4 patterns your specific finding belongs to; §6 is the checklist your own report must
   satisfy.
4. `dev/specs/{SPEC_PATH}` — YOUR SPEC, full detail, including the exact UI call-site it
   specifies
5. Whatever source files your spec names — read them in full before editing, don't guess at
   existing conventions (visual style, error-handling pattern, naming) — match what's already
   there.

## Hard Rules

- Build exactly what the spec scopes. If you notice another BLT finding while working, note it
  in your report — do not fix it in this pass; that's scope creep across lanes that may be
  running concurrently in other windows.
- `static/index.html` and `src/web.py` are shared files other concurrent lanes may also be
  touching — before editing, check `git diff` against what you expect; if something unexpected
  is already there, it's likely another lane's in-flight work, not a bug. Don't revert it.
- State the exact new UI call site (file:line) in your report — this is not optional. This is
  precisely the thing the audit found missing everywhere else.
- Do not claim "reachability-verified" unless you actually opened the served app and clicked
  through it. If you only curled the endpoint, say "correctness-verified only" and name why
  reachability-verification wasn't possible in your environment.
- Do not commit — leave everything staged for operator.
- No real student/teacher data anywhere, including in any new test fixtures.

## Verification Before Closing

```bash
python3 -m pytest -q tests/
python3 -m py_compile src/web.py   # if backend touched
python3 scripts/check_ui_contract.py --bump   # if static/index.html or src/web.py touched
python3 -m src.lv_cli serve 8787   # then reachability-verify live, per §Execution Contract step 4
```

## Deliverables

1. Working code for {SPEC_ID}'s scope.
2. Short report (inline in your final response is fine for a spec this size — a separate
   `dev/reports/` file only if the spec's own scope is large enough to warrant one).
3. `dev/INDEX.md` updated.

## Final Response

Under 150 words. Include only:
- what was built, and the exact new UI call site (file:line)
- correctness-verified vs. reachability-verified, explicitly labeled, for each claim
- test result
- anything noticed but deliberately not fixed (scope discipline)

Do not restate the whole task.
```
