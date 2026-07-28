# SPEC — Drive Self-Service Sign-In + New-Files Check (Phase 2 ruling proposal)

**Date:** 2026-07-27 (night before teacher day 1)
**Status:** §A BUILT 2026-07-27 (same night, post-approval) — UI contract v44,
`google_drive_oauth.py` + `load_settings()` seam + auth routes + Sources/Drive
sign-in panel, 33 new tests. §B approved as the Phase 2 ruling but builds in its
OWN window (it touches the daily-file renderer the Slack-ops lane owns — avoid
another v38-style seal collision). Uncommitted, awaiting operator commit window;
operator checklist §C still open (OAuth client creation + consent-screen
"In production (unverified)").
Approval history: APPROVED WITH AMENDMENTS (v2) — two-reviewer adjudication
2026-07-27 (Codex + Claude, forwarded by operator). Amendments are folded into
the sections below; adjudication record in §E.
**Relates to:** `SPEC_LV_DRIVE_WORKSPACE_2026-07-27.md` (Phase 1 built, v34–v42;
Phase 2 auto-sync was left as OPERATOR RULING REQUIRED — §B below is that ruling,
now approved), `HARDENING_LOOP_DRIVE_2026-07-27.md` (Drive surface hardened tonight).

## 0. What tonight's blocker actually is

The Drive round-trip works, but only if five env vars are hand-set
(`LV_GOOGLE_DRIVE_ENABLED/CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN/DRIVE_ROOT_ID`),
and the refresh token must be hand-crafted via OAuth playground. That is:

- impossible for teachers (frozen desktop app has no env-var story at all),
- painful for the operator (playground round-trip per machine),
- fragile (refresh token in shell profile; scope mistakes surface as opaque 403s).

Of the four open items from tonight:

| Item | Buildable? |
|---|---|
| Drive env creds | **YES — this spec, §A.** Replace env-var plumbing with in-app Google sign-in. |
| Phase 2 auto-sync ruling | **YES — §B** proposes the ruling; approving this spec = the ruling. |
| Christi's folder link | No — external info. But with §A + Phase 1 URL-paste, Christi can paste it herself. |
| Commit + desktop release | No — operator-only (commit window; PUSH = downloadable, AGENTS.md rule 0). §C is the checklist. |

## A. In-app Google sign-in (self-service credentials)

### A1. Flow (OAuth 2.0 installed-app, loopback + PKCE)

1. Teacher clicks **"Sign in with Google"** in the Drive section's Not-connected panel.
2. Backend `POST /api/google-drive/auth/start`:
   - generates PKCE verifier/challenge (S256) + random `state`,
   - starts a **one-shot loopback listener** on `127.0.0.1:<ephemeral>` (120 s timeout),
   - returns the `accounts.google.com` auth URL; UI opens it in the browser.
3. Google redirects to the loopback with `code` + `state`. Listener validates
   `state`, exchanges the code for tokens **locally** (stdlib urllib, same
   `DriveTransport` seam), shows a plain "You can close this tab" page, exits.
4. Refresh token + client config persist to
   `~/.lingua-viva/config/google_drive.json`, **0600 via the existing
   `_atomic_write_private_json`** (hardening-loop helper). Override:
   `LV_GOOGLE_DRIVE_AUTH_PATH` (conftest gets the hermetic line, same pattern
   as tonight's `LV_LOCAL_IMPORTS_DIR`).
5. `POST /api/google-drive/auth/disconnect` deletes the stored token (and
   best-effort revokes it at `oauth2.googleapis.com/revoke`).

**Completion wiring (review amendment — Claude gap 3):** the browser flow
finishes out-of-band, so the UI must learn about it explicitly:
- After `auth/start`, the Drive panel **polls `GET /api/google-drive/status`**
  (every 2 s, up to the 120 s listener timeout) and re-renders to
  "Signed in as …" when `configured` flips true.
- **Double-click safety:** `auth/start` cancels/replaces any pending listener
  (one flow at a time; starting a new flow invalidates the old `state`).
- **Desktop shell:** the dynamic `accounts.google.com/...` auth URL must
  actually open — the backend opens it via Python `webbrowser.open` (works in
  browser and Electron modes alike) rather than relying on the desktop shell's
  `openExternal` allowlist in `main.ts`, which only permits known URL prefixes.
  The route ALSO returns the URL so the UI can render a "click here if nothing
  opened" fallback link.

**UX placement (review amendment — Codex, REQUIRED):** this does **not** live
only in Settings. The Drive connection and daily flow must be reachable from
the **Sources/Drive nav surface** — the sign-in button, signed-in-as line, and
disconnect live in the Drive section of the Sources view (where the
Not-connected panel already is). Settings may expose diagnostics and advanced
configuration, but daily use belongs in the main app. Otherwise we solve auth
while still hiding the workflow.

### A2. Settings resolution (single seam)

`settings_from_env()` becomes `load_settings()`:

```
env vars (operator override / tests / CI)  >  stored google_drive.json  >  unconfigured
```

All eight call sites already funnel through `settings_from_env`/`ensure_configured`
(google_drive_integration.py:181/377) — no other code changes. `status()` grows
`auth_source: "env" | "stored" | null` and `account_email` (for "Signed in as …"
display; requires `openid email` in the scope request — see §A4); still
secret-free (pinned by existing test).

**Env-shadowing trap (review amendment — Claude gap 5):** §C4 has the operator
setting env creds tonight as fallback, and env silently wins forever after — a
teacher who later clicks "Sign in with Google" would complete the whole dance
and see nothing change. Therefore: when `auth_source: "env"`, the Drive panel
renders **"Using credentials set up by whoever installed Lingua Viva"** and
**hides the sign-in button**. Sign-in is only offered when env creds are absent.

### A3. The one thing that stays operator-only (one-time, ~10 min)

Google will not let an app conjure an OAuth client. The operator creates **one
"Desktop app" OAuth client** in Google Cloud console. Every machine after that
is pure click-through.

**Client-config wording (review amendment — Codex):** the bundled desktop
client secret is *not a confidential server secret* — it is **app configuration
for Google's installed-app flow** and should be treated as public/discoverable.
The real protections are PKCE, state validation, loopback binding, token
storage, and revocation.

**Delivery mechanism (review amendment — Claude gap 1, REQUIRED):** this is a
**public repo** — the client_id/secret are **never committed**. They are
**injected at desktop-release build time** (CI secret → packaged
`oauth_client.json` inside the app bundle). For source/operator runs they come
from `LV_GOOGLE_OAUTH_CLIENT_ID`/`LV_GOOGLE_OAUTH_CLIENT_SECRET` env vars or a
local uncommitted `~/.lingua-viva/config/oauth_client.json`. Committing them
would invite quota abuse and phishing reuse of the client, and violate the
repo's own secret hygiene.

**Consent-screen gotcha (needs operator awareness):** if the consent screen
stays in **Testing** status, refresh tokens expire after **7 days** — teachers
would re-sign-in weekly. Publish it as **In production (unverified)** instead:
users see Google's "unverified app" interstitial once ("Advanced → continue"),
but tokens persist. With 3 teachers, verification is not worth pursuing now.
The Not-connected panel copy will walk through the interstitial in teacher
language.

### A4. Scope decision (operator input wanted)

- **`drive` (recommended):** lists/reads any folder shared with the signed-in
  account, uploads anywhere permitted. Matches how Phase 1 works today
  (paste any shared-folder URL).
- **`drive.file`:** far narrower, but it **cannot list Christi's shared folder**
  (only files the app itself created/opened) — it would break the core
  workflow unless we add a Google Picker dependency (external JS; conflicts
  with the local-first, stdlib-only posture).

**RULED (both reviewers): `drive` for the pilot**, with the mitigation that all
egress remains guarded by the Phase-1/hardening-loop controls (explicit import,
upload destination allowlist, privacy events, 0600 artifacts). Long-term
follow-up item: revisit `drive.file` + Google Picker as a narrower-scope
migration path once the pilot settles.

**Restricted-scope disclosure (review amendment — Claude gap 2):** `drive` is a
Google **restricted scope**. Unverified apps carry a **100-user grant cap**
(fine for 3 teachers, but a real ceiling), and later verification requires a
paid **CASA security assessment**, not the standard review. Operator approves
knowing the ceiling exists.

**Scope request:** `openid email https://www.googleapis.com/auth/drive` — the
`openid email` pair is what makes `account_email` (and the "Signed in as …"
line) reliable via the ID token.

**Teacher-facing trust copy (review amendment — Codex, verbatim):**

> Google may show a broad Drive permission. Lingua Viva only checks folders
> you connect, and it does not download file contents until you choose to
> import.

### A5. Root folder no longer required

With sign-in + Phase 1's URL-paste folder connect, `LV_GOOGLE_DRIVE_ROOT_ID`
becomes optional: the school shared folder is just a connected folder.
`can_upload` becomes `configured AND (root_id OR connected folders exist)` —
the UI's share-back panel already behaves this way; backend `status()` catches up.

### A6. Security posture

PKCE S256 + `state` check; listener bound to 127.0.0.1 only, one-shot, 120 s
timeout; tokens never logged or echoed in any response (only booleans/account
email); stored file 0600-from-birth; revoke on disconnect; privacy events
`drive_account_connected` / `drive_account_disconnected` (generic detail copy,
consistent with tonight's three new event types).

**Refresh-token death path (review amendment — Claude gap 4, REQUIRED):** the
spec's own motivation is "scope mistakes surface as opaque 403s" — so token
death must not reproduce that. When the token refresh fails with
`invalid_grant` (revocation, password change, 6-month idle, Testing-mode
expiry): `status()` reports `needs_signin: true`, and the Drive panel shows a
plain **"Sign in again"** state — never an opaque 403/503. Applies only to
`auth_source: "stored"`; env-sourced failures keep today's operator-facing
message.

**Deferred hardening (review amendment — Codex, named-not-blocking):** replace
JSON refresh-token storage with **platform keychain/credential vault** before
any broad school deployment. 0600 JSON is accepted for the pilot.

### A7. Build items

`google_drive_oauth.py` (new module: PKCE, loopback server, token exchange,
`openid email` ID-token parse for account_email, stored-config read/write,
client-config resolution env → local file → bundled, revoke,
`needs_signin` detection on `invalid_grant`) · `load_settings()` precedence in
`google_drive_integration.py` · 2 new routes + `status()` fields
(`auth_source`/`account_email`/`needs_signin`) in `web.py`, auth URL opened
backend-side via `webbrowser.open` and returned for the fallback link ·
Drive-section UI **in the Sources view** (Codex amendment): "Sign in with
Google" button + trust copy, status polling to "Signed in as …", "Sign in
again" state, disconnect, env-override state hides sign-in · conftest hermetic
override (`LV_GOOGLE_DRIVE_AUTH_PATH`) · tests (loopback flow with fake
transport, state mismatch rejected, timeout, double-start replaces flow,
precedence incl. env-shadowing, invalid_grant → needs_signin, revoke, status
secret-freeness) · ceremony: contract bump + bump-log + EXPECTED_VERSION +
ROUTE_REACHABILITY entries. **Desktop note:** flow must work from the frozen
app (backend opens browser; loopback is in-process — no packaging change
expected beyond CI-injected `oauth_client.json`).

## B. Phase 2 ruling proposal — "New from Drive" WITHOUT flipping the privacy posture

The published posture is `mode: explicit_import` — no content reaches the
machine without a teacher choosing it. The original auto-sync draft flips that.
Proposal: **don't flip it.** Split "check" from "import":

- **Check = metadata only.** On app open (and via a "Check now" button), list
  connected folders' files and compare `modifiedTime` against `last_checked`.
  **No file content moves.** This is the same class of call the folder-connect
  verify already makes.
- Surface: badge on the Sources/Drive nav ("3 new"), a **New from Drive** list
  per folder card, and a "New From Drive" section in the daily file alongside
  Slack ops.
- **Import stays explicit:** each new-file row ends in the existing
  "Bring this file in" → "Review now" chain. Student-evidence folders keep
  mandatory review regardless.
- Privacy event `drive_new_files_checked` (metadata check ran; generic detail
  makes clear no content moved). Threat-model/copy: one added sentence —
  "Lingua Viva may look at file *names and dates* in folders you connected, to
  tell you what's new; it never downloads content without you."
- **Deferred (not in this build):** timed background cadence and any
  auto-*download* mode. If teachers ask for true keep-updated later, that
  returns as its own posture-change spec.
- **Robustness (review amendments — Claude minor):** the on-open check is
  **fail-open and non-blocking** — an offline day-1 classroom must never hang
  startup (fire-and-forget after render, errors swallowed to a quiet "couldn't
  check" hint). New-file detection keys on **Drive's `modifiedTime` vs a stored
  per-folder high-water mark** (the max `modifiedTime` seen), not local
  wall-clock — immune to clock skew.
- **Sequencing (review ruling):** §B builds in its **own window**, after §A
  ships — it touches the daily-file renderer owned by the Slack-ops lane.

**Approving §B as written = the Phase 2 ruling** (posture preserved, convenience
delivered). Build items: on-open + on-demand check, changed-file detection vs
`last_checked`, badge + folder-card list + daily-file section, event type,
tests, ceremony.

## C. Operator-only checklist (no agent build; for tomorrow morning)

1. Google Cloud: create Desktop-app OAuth client; publish consent screen
   **In production (unverified)** (§A3); note client_id/secret for app config.
2. Commit window: tonight's tree (Drive workspace + 3 hardening lanes,
   contract v42, suite 1121/13) + this spec's build once approved.
3. Desktop release: per `PUSH_TO_PRODUCTION.md` / AGENTS.md rule 0 — teachers
   have nothing until the download link serves the new build.
4. Christi: with §A shipped she signs in and pastes her folder link herself;
   until then, collect the link + set env creds as tonight's fallback.

## D. Open questions — RULED (see §E)

1. §A4 scope: **`drive` for pilot**; long-term revisit `drive.file` + Picker.
2. §A3: **bundled Desktop-app client OK**, documented as non-confidential app
   config, **conditional on build-time injection — never committed** (public repo).
3. §B: **approved as written** — metadata-only "New from Drive"; posture preserved.
4. Sequencing: **§A first, alone.** Env-creds fallback (§C4) covers day 1; §A
   ships in the day-2 release; §B in its own window (daily-file renderer is
   Slack-ops lane territory).

## E. Adjudication record (2026-07-27)

Two independent reviews forwarded by operator; both **approve with amendments**;
zero conflicts between them on any ruling.

- **Codex** — verified Google-side assumptions against current docs (loopback
  OAuth supported for desktop; `drive.file`+Picker is Google's recommended
  narrow path; Testing-mode 7-day token expiry is real). Required amendment:
  daily flow lives in Sources/Drive nav, not Settings (§A1). Others: secret-is-
  app-config wording (§A3), teacher trust copy (§A4), keychain deferral (§A6).
- **Claude** — approve-with-edits; 5 gaps, all folded in: (1) client-config
  build-time injection, never committed (§A3); (2) restricted-scope
  disclosure — 100-user cap / CASA (§A4); (3) UI completion wiring — status
  polling, double-click cancel, backend `webbrowser.open` vs Electron
  allowlist (§A1); (4) refresh-token death path → `needs_signin`, plus
  `openid email` scopes (§A6/§A4); (5) env-shadowing — hide sign-in button
  under `auth_source: "env"` (§A2). Minor: §B fail-open non-blocking check +
  modifiedTime high-water mark (§B).

Build authorization: **§A now** (this window). §B: approved, next window.
