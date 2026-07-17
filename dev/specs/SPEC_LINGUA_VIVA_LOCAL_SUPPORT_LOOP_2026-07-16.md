# Lingua Viva Local Support Loop Spec

**Status**: proposed build spec  
**Date**: 2026-07-16  
**Branch**: `LINGUA-VIVA-UPDATE`  
**Purpose**: Build a local customer-service / IT-service loop that teachers can run before escalating support, especially across time zones.

## 0. One-Sentence Goal

Give teachers a safe local command that can diagnose, update, repair, validate, and package support evidence for Lingua Viva and related learning-architecture tools without leaking student data or mutating curriculum authority.

## 1. User Story

A teacher in a different time zone is stuck. Before calling the operator at 3am, they open the Lingua Viva app and press:

```text
Doctor / Fix My App
```

The app runs the local support-loop engine, checks the installation, identifies known issues, fixes safe problems after user confirmation, pulls approved updates when requested, validates the system, and produces a private redacted support bundle if it cannot solve the issue.

The teacher should end with one of three outcomes:

1. Problem fixed locally.
2. Clear next step with exact command.
3. Redacted support bundle ready to send.

## 2. Product Boundary

This support loop is not part of the Lingua Viva curriculum package itself. It is a local tool layer behind the existing Lingua Viva app. The app button is the primary teacher UX; CLI commands are the underlying engine surface for development, debugging, CI, and operator support.

Recommended implementation home:

```text
/home/mical/learning-architecture/src/education/support_loop/
```

or, if this repo remains the active monorepo for deployment tooling:

```text
/home/mical/fde/implementations/education/lingua-viva/dev/support_loop/
```

The tiny Lingua Viva package should continue to own curriculum artifacts, publication rules, claim/evidence registers, and gauntlets. The support loop may read those files, run checks, and propose repairs. It must not turn Lingua Viva into a platform.

## 3. Non-Negotiable Constraints

- Never upload student data.
- Never include raw student observations, names, IEPs, progress reports, individual scores, or parent communications in support bundles.
- Never silently edit `.docx`.
- Never promote `curriculum/lingua_viva_matrix.yaml` to authoritative.
- Never rewrite curriculum content automatically.
- Never make external research calls with unpublished curriculum structure.
- Never run destructive Git commands such as `reset --hard`, `checkout --`, or clean without explicit operator approval.
- Never overwrite teacher-local data during update or repair.
- Every auto-fix must be explainable, reversible, and logged.

## 4. Operating Modes

### 4.1 Teacher Mode

Default. Safe commands only.

Allowed:

- diagnose
- safe repair
- update from approved source
- run gauntlets
- build redacted support bundle

Blocked:

- curriculum-source edits
- schema migrations without known migration ID
- matrix promotion
- deleting files
- sending logs externally
- unredacted support bundle

### 4.2 Operator Mode

Requires explicit flag:

```bash
lv support --operator
```

Allowed:

- approve risky repair
- run migration
- accept new known-fix rule
- review redacted bundle
- mark incident resolved

Operator mode still does not allow silent student-data export.

### 4.3 CI Mode

For release validation.

```bash
lv gauntlet --ci
```

Allowed:

- deterministic validation
- no interactive prompts
- no repair unless `--safe-repair` is explicitly set
- machine-readable JSON report

## 5. App And Command Surface

### 5.0 App Button: Doctor / Fix My App

Primary teacher surface.

Button label options:

- `Doctor`
- `Fix My App`
- `Run Health Check`

Recommended first label: `Doctor`.

Button behavior:

1. Run the same local engine as `lv doctor`.
2. Show a short teacher-readable status.
3. Offer only safe next actions:
   - `Fix safe issues`
   - `Update app`
   - `Run validation again`
   - `Create support bundle`
   - `Contact support`
4. Never expose raw logs by default.
5. Never upload anything automatically.
6. Require explicit confirmation before repair, update, or support-bundle creation.

App states:

| State | App copy | Allowed actions |
|---|---|---|
| `OK` | "Everything looks healthy." | run again, view details |
| `WARN` | "Something may need attention, but you can keep working." | view details, create support bundle |
| `FIXABLE` | "I found a safe fix." | fix safe issues, view details |
| `UPDATE_AVAILABLE` | "An approved update is available." | update app, defer |
| `BLOCKED` | "I cannot fix this safely on my own." | create support bundle, contact support |
| `PRIVATE_RISK` | "I found a privacy risk and stopped." | quarantine if safe, create redacted support bundle |

The CLI remains useful, but teachers should not need Terminal for the normal support flow.

### 5.1 `lv doctor`

Underlying local engine and developer/operator fallback.

```bash
lv doctor
lv doctor --json
lv doctor --with-repair
```

Responsibilities:

- detect install root
- identify repo/package versions
- detect active branch and dirty worktree state
- verify required Lingua Viva files
- parse YAML/NDJSON
- run Lingua Viva artifact gauntlet
- check learning-architecture runtime availability if present
- check local data path health without reading raw sensitive contents into output
- detect stale structured artifacts relative to source-of-truth rules
- detect obvious public/private boundary issues
- summarize status in teacher-readable language

Output levels:

- `OK`: no action needed
- `WARN`: action recommended but not blocking
- `FIXABLE`: safe repair available
- `BLOCKED`: needs operator or support bundle
- `PRIVATE_RISK`: stop and do not proceed until reviewed

### 5.2 `lv repair --safe`

Applies known safe fixes only.

Safe fixes include:

- create missing empty non-sensitive directories
- restore missing generated cache/index files
- normalize YAML formatting if semantic-equivalent
- rebuild local search/index caches
- refresh derived non-authoritative manifests
- repair executable bit on local checker scripts
- quarantine files that accidentally appear in public output directories
- regenerate support-loop metadata

Unsafe fixes requiring operator approval:

- editing README/public wording
- editing claim/evidence register
- editing curriculum matrix
- editing `.docx`
- changing publication-safety rules
- changing assessment/rubric thresholds
- deleting files
- applying Git conflict resolution
- running migrations against local student-data stores

### 5.3 `lv update`

Safely updates local tool/curriculum package.

```bash
lv update
lv update --check
lv update --dry-run
lv update --source origin/LINGUA-VIVA-UPDATE
```

Required behavior:

- detect local modified files
- refuse to update if private data may be at risk
- preserve local teacher data
- fetch approved remote
- show update plan
- apply update only from allowed branch/tag/release
- run post-update gauntlet
- rollback update if validation fails where rollback is safe
- otherwise create support bundle with failure state

No update may overwrite local student data.

### 5.4 `lv gauntlet`

Runs validation gates.

```bash
lv gauntlet
lv gauntlet --ci
lv gauntlet --json
```

Required gates:

- Lingua Viva artifact gauntlet
- YAML/NDJSON schema checks
- README public-claim scan
- publication-safety rule presence
- matrix non-authoritative status
- `.docx` unchanged/authority check
- local data privacy scan by path and filename, not raw content upload
- support bundle redaction test
- no MC-bloat active-surface scan
- command health check

### 5.5 `lv support-bundle`

Creates a redacted support package.

```bash
lv support-bundle
lv support-bundle --include-screenshots
lv support-bundle --operator-review
```

In the app, this appears as `Create support bundle`.

Contents:

- `SUPPORT_SUMMARY.md`
- command outputs from `lv doctor`
- failed checks
- version/branch info
- active config keys, values redacted when sensitive
- list of local files by path/status, excluding private directories
- redacted traceback/log excerpts
- gauntlet JSON output
- repair attempts and results

Forbidden bundle contents:

- raw observations
- student names
- raw student work
- IEP/progress report content
- parent messages
- unredacted `.docx`
- unpublished curriculum structure unless explicitly approved by operator
- API keys, tokens, passwords, OAuth secrets

### 5.6 `lv incident`

Records and classifies issues.

```bash
lv incident list
lv incident show INCIDENT_ID
lv incident resolve INCIDENT_ID
```

Incident classes:

- `install_missing_dependency`
- `repo_update_conflict`
- `artifact_missing`
- `yaml_schema_error`
- `revision_log_schema_error`
- `gauntlet_failure`
- `privacy_risk`
- `source_artifact_drift`
- `local_data_permission`
- `runtime_config_error`
- `network_unavailable`
- `unknown`

### 5.7 `lv improve`

Operator-facing improvement proposal loop.

```bash
lv improve analyze
lv improve propose
lv improve accept INCIDENT_ID
```

Responsibilities:

- review incidents and failed gauntlets
- identify repeated issues
- propose new known-fix rules
- propose new gauntlet checks
- propose documentation improvements
- never auto-promote a repair rule without operator approval

## 6. System Architecture

### 6.1 Components

```text
support_loop/
  cli.py
  doctor.py
  update.py
  repair.py
  gauntlet.py
  bundle.py
  incident.py
  improve.py
  privacy.py
  git_safe.py
  schemas.py
  rules/
    known_fixes.yaml
    privacy_patterns.yaml
    allowed_update_sources.yaml
  templates/
    SUPPORT_SUMMARY.md.j2
    INCIDENT.md.j2
```

### 6.2 Data Directory

Local support state should live outside public curriculum files:

```text
.lv_support/
  incidents.ndjson
  repair_log.ndjson
  doctor_runs.ndjson
  bundles/
  cache/
```

`.lv_support/` should be gitignored if placed in a repo.

### 6.3 Config

```yaml
version: "2026-07-16"
mode: teacher
allowed_update_sources:
  - origin/LINGUA-VIVA-UPDATE
private_paths:
  - "**/student_lens*.db"
  - "**/observations*"
  - "**/parent_reports*"
  - "**/progress_reports*"
  - "**/IEP*"
public_artifact_roots:
  - "implementations/education/lingua-viva"
required_gauntlets:
  - "implementations/education/lingua-viva/dev/lv_artifact_gauntlet.py"
```

## 7. Privacy Model

### 7.1 Redaction Classes

Support bundle redactor must detect:

- student names where possible
- emails
- phone numbers
- addresses
- API keys/tokens
- filenames indicating student records
- parent report content
- raw observation transcript patterns
- database paths
- `.docx` content snippets

### 7.2 Path-Level Protection

Some paths should be excluded entirely from bundle content:

```text
**/student_lens*.db
**/still_i_rise.db
**/observations*
**/parent_reports*
**/progress_reports*
**/IEP*
**/private*
```

The bundle can report:

```text
Excluded private path: case-studies/04-still-i-rise/data/still_i_rise.db
Reason: local student data store
```

It must not include contents.

### 7.3 External Calls

Default support loop is local-only.

No command may send support data externally unless:

- operator explicitly approves;
- bundle has passed redaction;
- bundle manifest lists exactly what will be sent;
- user confirms transmission.

## 8. Git Safety

### 8.1 Allowed Read Commands

- `git status --short --branch`
- `git rev-parse`
- `git branch --show-current`
- `git fetch --dry-run`
- `git diff --name-only`
- `git log -n`

### 8.2 Allowed Mutating Commands In Teacher Mode

- `git fetch`
- `git pull --ff-only` from approved branch, only after preflight passes

### 8.3 Blocked Without Operator Approval

- `git reset --hard`
- `git checkout --`
- `git clean`
- non-fast-forward pull
- merge conflict auto-resolution
- force push

### 8.4 Update Preflight

Before any update:

- identify branch
- identify remote
- detect dirty worktree
- detect private data paths
- create pre-update support snapshot
- dry-run gauntlet if possible
- explain exact update plan

## 9. Known-Fix Rule Format

```yaml
- id: lv-fix-001
  name: restore_missing_lingua_viva_dev_dir
  issue_class: artifact_missing
  mode: teacher
  risk: low
  matches:
    missing_path: "implementations/education/lingua-viva/dev"
  actions:
    - type: mkdir
      path: "implementations/education/lingua-viva/dev"
  blocked_if:
    - path_matches_private_pattern: true
  proof:
    - run: "lv gauntlet --json"
  rollback:
    - type: rmdir_if_empty
      path: "implementations/education/lingua-viva/dev"
```

Known-fix rules must be reviewed before release.

## 10. Improvement Loop

The support loop may improve the support system, not the curriculum, without review.

### 10.1 Analyze

Inputs:

- failed doctor runs
- incident log
- gauntlet failures
- support-bundle summaries
- repeated manual fixes

Outputs:

- `dev/support_improvement_candidates.yaml`
- suggested known-fix rule
- suggested documentation patch
- suggested gauntlet check

### 10.2 Propose

Each proposal includes:

- problem
- evidence
- affected teachers/tool versions
- proposed fix
- privacy impact
- rollback plan
- tests
- operator approval status

### 10.3 Accept

Only operator can promote:

- new known-fix rule
- new gauntlet rule
- new update source
- new migration

## 11. Gauntlet Design

### 11.1 Local Tool Gauntlet

Required checks:

- CLI imports
- command help output
- config parse
- privacy patterns parse
- known-fix rules parse
- dry-run doctor on fixture repo
- safe repair on fixture repo
- support bundle redaction fixture
- update preflight fixture
- blocked destructive command fixture
- incident logging fixture
- improvement proposal fixture

### 11.2 Lingua Viva Artifact Gauntlet

Reuse:

```bash
python3 implementations/education/lingua-viva/dev/lv_artifact_gauntlet.py
```

### 11.3 Support Bundle Redaction Gauntlet

Fixtures should include fake but realistic:

- student names
- emails
- IEP filenames
- parent report snippets
- API key strings
- `.docx` text snippets
- observation transcripts

Expected:

- bundle excludes private files
- bundle redacts sensitive tokens
- bundle includes enough diagnostic context

## 12. Teacher UX

Teacher UX is app-first. CLI examples below describe equivalent engine behavior and support/debug messages.

### 12.0 App Flow

```text
[Doctor]
  -> Running local checks...
  -> Status: FIXABLE
  -> "I found 2 safe fixes: rebuild local cache, refresh validation index."
  -> Buttons: [Fix safe issues] [Create support bundle] [Details]
```

If repair succeeds:

```text
All fixed.
Validation passed.
You can keep working.
```

If repair fails:

```text
I could not fix this safely.
I created a redacted support bundle you can send.
No student data was included.
```

### 12.1 Successful Doctor Run

```text
Lingua Viva Doctor: OK

Checked:
- app files
- curriculum package
- local config
- privacy boundaries
- update status

No action needed.
```

### 12.2 Fixable Issue

```text
Lingua Viva Doctor: FIXABLE

Problem:
- Local cache is missing.

Safe fix available:
- Rebuild local cache.

Run:
  lv repair --safe
```

### 12.3 Blocked Issue

```text
Lingua Viva Doctor: BLOCKED

Problem:
- Local repo has uncommitted changes in curriculum files.

I will not pull updates automatically.

Next:
  lv support-bundle
```

### 12.4 Privacy Risk

```text
Lingua Viva Doctor: PRIVATE_RISK

Problem:
- A file that looks like student data is in a public artifact path.

I did not read or upload it.

Next:
  lv repair --safe
```

## 13. Build Phases

### Phase A - Diagnostic MVP

Deliver:

- app `Doctor` button wired to local doctor engine
- `lv doctor` CLI fallback
- config discovery
- branch/status checks
- file presence checks
- YAML/NDJSON parse
- existing LV artifact gauntlet integration
- JSON and Markdown report output

Acceptance:

- teacher can press one app button and know status
- CLI returns the same status for debugging
- no mutations
- no support bundle yet

### Phase B - Support Bundle

Deliver:

- redacted bundle builder
- privacy path exclusions
- redaction fixtures
- bundle manifest

Acceptance:

- bundle contains useful diagnostics
- no private content included
- redaction gauntlet passes

### Phase C - Safe Repair

Deliver:

- `lv repair --safe`
- known-fix rule engine
- repair log
- rollback metadata
- post-repair gauntlet

Acceptance:

- only low-risk fixes run in teacher mode
- every repair logged
- failures produce bundle guidance

### Phase D - Safe Update

Deliver:

- `lv update --check`
- `lv update --dry-run`
- approved source list
- fast-forward-only update path
- dirty worktree handling
- post-update validation

Acceptance:

- local data protected
- update refuses risky state
- validation failure produces support bundle

### Phase E - Improvement Proposals

Deliver:

- incident classifier
- repeated-failure analyzer
- proposal generator
- operator approval workflow

Acceptance:

- loop proposes improvements
- nothing self-promotes
- new rules require operator review

### Phase F - Teacher Packaging

Deliver:

- app button UX polish
- one-click command wrapper only as support fallback
- installation instructions
- cross-platform smoke tests
- teacher-facing docs

Acceptance:

- non-technical teacher can run doctor, repair, update, and bundle from the app
- support/operator can run equivalent CLI commands
- failure messages are actionable

## 14. Acceptance Criteria

Overall system is acceptable when:

- the app Doctor button runs locally with no external calls.
- `lv doctor` provides the same local engine behavior for support/debug use.
- `lv repair --safe` applies only reviewed low-risk fixes.
- `lv update` refuses destructive or privacy-risk states.
- `lv gauntlet` validates active artifacts and local support tooling.
- `lv support-bundle` produces useful redacted diagnostics.
- no support path includes raw student data.
- no command silently edits `.docx`.
- no command promotes curriculum matrix authority.
- every repair/update incident is logged.
- new known-fix rules require operator review.
- teacher-facing output is clear enough to use before escalation.

## 15. Test Plan

### Unit Tests

- config parsing
- privacy pattern matching
- redaction
- known-fix matching
- safe command allowlist
- blocked command denylist
- incident classification
- support bundle manifest generation

### Integration Tests

- doctor on healthy fixture
- doctor on missing file fixture
- doctor on dirty repo fixture
- repair safe missing cache
- update dry-run on clean fixture
- update refused on dirty curriculum file
- support bundle excludes private paths
- gauntlet catches README overclaim

### Adversarial Tests

- fake API key in config
- fake student name in log
- fake IEP filename
- fake parent report snippet
- fake `.docx` curriculum excerpt
- malicious file asking tool to ignore instructions
- symlink pointing private file into public folder

## 16. Metrics

Track locally:

- number of doctor runs
- issue classes seen
- safe repairs attempted
- safe repairs succeeded
- support bundles generated
- update failures
- repeated incident classes

Do not track:

- student names
- student outcomes
- raw observations
- parent communications
- private curriculum excerpts

## 17. Open Questions

- Where should the support tool live: learning-architecture, fde, or a standalone package?
- Which branch/tag is the teacher-safe update source?
- What is the first supported teacher OS: macOS only, or macOS + Windows?
- Should support bundles be local zip files only, or optionally uploaded after approval?
- Who signs new known-fix rules?
- What local data stores exist in the actual teacher app?
- What app framework owns the Doctor button and local command execution?
- Should the app call a bundled Python module, a local subprocess, or a native service wrapper?

## 18. Non-Goals

- Autonomous curriculum rewriting.
- Autonomous assessment/rubric changes.
- Cloud helpdesk integration in v1.
- Automatic upload of support bundles.
- Live remote control of teacher machines.
- Full MDM/device-management.
- Replacing human pedagogical judgment.
- Promoting structured curriculum source.

## 19. Final Recommendation

Build this in phases behind the existing Lingua Viva app. Start with the app `Doctor` button and support-bundle creation, because they reduce 3am calls without creating repair risk. Keep `lv doctor` as the same engine exposed for support/debug use. Add safe repair only after real incidents identify safe fixes. Add update after dirty-worktree and local-data protection are proven. Add recursive improvement last, as an operator-reviewed proposal system rather than an autonomous patcher.
