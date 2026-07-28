# SPEC — Drive Stack Final Hardening (post-§A full review)

**Date:** 2026-07-27 (late night, after §A sign-in landed at contract v44)
**Status:** H1–H5 BUILT 2026-07-27 (operator approved "get this across the
line" with the recommended §5 rulings: Q1 = 100 MB cap; Q2 = prune exports
to 3/student, imports never pruned; Q3 = interstitial copy approved
verbatim; Q4 = single window). Sealed at UI contract v46. 18 new tests
(17 in test_google_drive_integration.py + loopback-listener-cleanup pin in
test_google_drive_oauth.py) + 3 UI pins. Bonus fix found in-window:
web.py materialize wrote student lens snapshots with default umask — now
0600-from-birth via _atomic_write_private_json. H6 remains PARKED with
desktop-release work. Uncommitted — operator commit window.
**Relates to:** `SPEC_LV_DRIVE_WORKSPACE_2026-07-27.md` (Phase 1 complete),
`SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27.md` (§A built v44; §B approved,
queued for its own window), `HARDENING_LOOP_DRIVE_2026-07-27.md`.

## 0. Review summary (what this spec is based on)

Full two-track review of the Drive stack (v34→v44, uncommitted):
backend/security (`google_drive_integration.py` 807 lines,
`google_drive_oauth.py` 324 lines, 8 web.py routes, 85 tests) and
UI/spec-drift (Sources→Drive section, §A drift table, ceremony v40–v44).

**Confirmed good — do not churn:** all 5 pre-build review gaps implemented and
tested (no committed client secret; `invalid_grant` → `needs_signin` state;
status polling + double-click flow replacement; loopback 127.0.0.1/one-shot/
120 s/state/PKCE-S256; env-shadowing surfaced via `auth_source` with sign-in
button hidden under env). SSRF, path traversal, token revocation, secret-free
errors, concurrency locks, public-repo hygiene: all pass with tests. Ceremony
coherent: v44 bump-log real, `EXPECTED_VERSION = 44`, ROUTE_REACHABILITY
call-site literals verified against index.html.

## 1. Start-over reflection (what we'd do differently — and what it implies now)

Asked honestly: *if starting from scratch tonight, what changes?*

1. **Auth first, features second.** We built import/upload/workspace on
   hand-set env tokens, then retrofitted sign-in. It worked only because
   everything funneled through one settings seam — but the retrofit is why
   env-shadowing complexity, the "operator sets env creds as fallback" trap,
   and bolted-on `auth_source` exist at all. *Lesson recorded; no rework
   warranted — the seam absorbed it.*
2. **Decide information architecture before building panels.** Drive UI moved
   three times in one day (Settings v34 → own view v36 → Sources panel v39),
   each move a contract bump, one a seal collision (v38). Sources-as-home was
   implicit from the start; building it first would have deleted two
   relocations. *Lesson for future surfaces: name the destination view first.*
3. **One lane per protected file per window.** v34→v44 in a day across ≥4
   concurrent lanes produced the v38 in-flight seal. → §4 sequencing rule.
4. **Design artifact lifecycle with the artifact.** `drive_imports/` and
   `drive_exports/` accumulate forever; nothing ever deletes. Retention should
   have been part of the first import spec. → H3.
5. **Bounded transport from day one.** Timeouts exist everywhere but byte
   limits nowhere; "how big can this response be" should be part of every
   transport method's signature. → H2.

Keep unchanged (validated by the review): the `DriveTransport` seam (made 85
hermetic tests possible), metadata-first privacy split (§B inherits it),
stdlib-only posture, single `load_settings()` seam.

## 2. Hardening items (ranked)

### H1 — Unverified-app interstitial walkthrough copy (P0, spec-promise unmet)
§A3 promised: "The Not-connected panel copy will walk through the interstitial
in teacher language." It is absent (index.html sign-in panel ~:2160–2169 has
only the broad-permission trust copy). Add 1–2 sentences before day-1 use:
Google will show a "Google hasn't verified this app" screen once; tap
**Advanced → Go to Lingua Viva (unsafe)** — this appears because Lingua Viva
is a small local app, not a published web service; nothing is shared until you
choose. Teacher language, no jargon. UI-contract bump required.

### H2 — Download size cap (P1)
`get_bytes()` (google_drive_integration.py:641) has a 30 s timeout but no
content-length guard; a huge file exhausts memory. Add: check Content-Length
when present, and hard-cap chunked reads at **100 MB** (proposed — see §5)
regardless. Over-limit → friendly import error ("This file is too large for
Lingua Viva to bring in") with a stable `code: "file_too_large"`. Fake-transport
tests: over-limit header, over-limit stream without header.

### H3 — Export/import retention (P1)
`drive_exports/` accumulates a timestamped lens snapshot per upload, forever.
After a successful upload, prune to the **3 newest** exports per student
(proposed). Same pass: document (not delete) `drive_imports/` retention as
teacher-owned — imports are working materials; add a line to the privacy copy
if needed. Test: fourth upload leaves exactly 3 files.

### H4 — Small defense-in-depth trio (P2, one sitting)
- Token-scrub guard: wrap transport calls so a raised exception can never
  carry the Authorization header into a traceback string.
- Query length bound: cap `list_files` query text at 1 KB pre-escape.
- Permissions test: assert `oauth_client.json` and `google_drive.json` are
  0600-from-birth (write path already uses the atomic helper; pin it).

### H5 — Test-coverage gaps (P2)
- Malformed Google responses (missing fields, wrong types) on list/import/
  token-exchange paths → friendly errors, no tracebacks.
- Concurrent import + disconnect race (revoked mid-import → clean failure).
- Crash/interrupt during loopback handshake → listener cleanup (believed
  covered by `finally`; pin it).

### H6 — Release-pipeline client-config injection (operator + CI, not agent-buildable alone)
Today's stopgap: operator places `oauth_client.json` or env vars per machine.
Final state: CI secret → injected into packaged desktop builds at release
time; never committed (public repo). Belongs with the next desktop-release
work per `PUSH_TO_PRODUCTION.md`; listed here so it isn't lost.

## 3. Explicitly out of scope
§B "New from Drive" (own approved window — touches the Slack-ops lane's
daily-file renderer); any auth-flow redesign; any scope change (`drive` stays,
per the ruling); Google verification/CASA (3 teachers, not worth it).

## 4. Sequencing & ceremony
Build **after** the operator's commit window seals v44 — this spec's H1 edits
index.html and must not repeat the v38 in-flight-seal collision. One lane, one
window, one contract bump (v45) covering H1–H5 together. H2/H3 add no routes;
H2's `code` field follows the filemap error-code pattern. Full ceremony:
bump-log, `EXPECTED_VERSION`, route-reachability re-check, full suite vs
current 1159/13 baseline.

## 5. Open questions for review
1. H2 cap: 100 MB right for real teaching artifacts (videos?), or lower/higher?
2. H3 retention: 3 per student OK? Prune imports too, or leave teacher-owned?
3. H1 wording: sign off the interstitial copy verbatim before build (it
   describes a scary Google screen — tone matters).
4. Fold H1 alone into the §B window instead (both touch the Drive panel), or
   keep all of H1–H5 in one hardening window as written?
