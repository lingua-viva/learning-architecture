# Install Verification — desktop-v0.2.11 (LV-5 startup blocker) — 2026-07-27

External install-testing trace, received 2026-07-27 evening. Preserved verbatim
below the resolution note.

## Resolution (build side, same night → desktop-v0.2.12)

- **LV-5 fixed**: `src/web.py` lines 979/980/1168 — `app.add_event_handler`
  → `app.router.add_event_handler` (app-level method removed in Starlette 1.0;
  router-level exists on both pre- and post-1.0). UI contract v50.
- **Installer deps pinned** in `desktop/electron/bootstrap.ts` to the exact
  set the 1301-test suite is validated against (fastapi 0.124.4 /
  starlette 0.50.0 / uvicorn 0.33.0 / httpx 0.28.1 / websockets 15.0.1 /
  pyyaml 6.0.3 / pdfplumber 0.11.9 / sqlite-vec 0.1.9). Exact pins make
  "Retry setup" deterministic — it converges to the known-good set instead of
  re-upgrading a fixed machine.
- **Backend-boot smoke gate** added to `.github/workflows/desktop-release.yml`:
  clean Python 3.12 + the exact pinned installer set, boots `src/web.py` the
  way Electron does, requires `/api/health` 200. Gates all platform builds.
- **Verified locally**: backend boots + `/api/health` 200 on BOTH
  starlette 0.50.0 (pinned) and starlette 1.3.1 / fastapi 0.139.2 (drifted,
  the broken-machine config) — so already-drifted machines work even before
  their next "Retry setup" re-pins them.
- Note: the fix pins were chosen as the *locally validated* versions
  (0.124.4/0.50.0), not the report's suggested 0.115.6/0.41.3 — pin what the
  suite actually ran against.

**Deferred (operator decisions, not in v0.2.12):** staple the `.app` inside
the DMG (needs pre-package staple ordering work), Linux button artifact choice
(CLI binary vs AppImage — currently intentional-ambiguous), `/api/health` as
full-doctor readiness probe vs lightweight liveness route.

---

# Original report (verbatim)

**Machine**: Apple Silicon, macOS 26.5, Python 3.12.7 (python.org framework — the interpreter the app resolves).
**Build under test**: `desktop-v0.2.11` (live from linguaviva.art, byte-perfect from GitHub).
**Method**: download harness → cryptographic build ID → DMG mount + static inspection → headless backend probe of every feature endpoint → live repro on the installed `.app`.
**Verdict**: Download/packaging layer is **perfect**. There is **one demo-blocker**: the Python backend crashes on startup on any current install.

## BLOCKER (LV-5) — backend crashes on startup: `app.add_event_handler` removed in Starlette 1.x

Symptom: "The local server did not start. This usually means a Python dependency is missing or port 8787 is busy." — misleading; port free, deps installed; backend crashes at import.

Crash (reproduced on the installed app):
```
/Applications/Lingua Viva.app/Contents/Resources/app/src/web.py, line 979, in <module>
    app.add_event_handler("startup", _startup_slack_ops)
AttributeError: 'FastAPI' object has no attribute 'add_event_handler'.
```

Root cause: unguarded module-top-level `app.add_event_handler` at web.py:979/980/1168; Starlette 1.0 removed the method from the application object. Reaches users because the Electron installer installs deps with no version constraints — fresh installs pulled fastapi 0.139.2 / starlette 1.3.1.

The retry/reinstall path could RE-BREAK a manually fixed machine (unpinned `pip install fastapi` re-upgrades starlette).

Crash exits cleanly — no orphaned process on 8787 (unlike old LV-3b).

## Download / packaging layer — all verified

- linguaviva.art serves desktop-v0.2.11; all 3 assets 200
- DMG byte-perfect: sha256 f8c0a1176b47cdb28faa79f8d7e4bfb5fd7824defc3d1a224b466a474df6634e, 95,296,359 B
- Staple-to-DMG fix (a944c3c): `stapler validate` on the DMG PASSED — LV-1 closed for the DMG
- Notarization/Gatekeeper accepted, Developer ID Mical Neill (XWT7RB624U), hardened runtime
- CFBundleShortVersion = 0.2.11; SmartScreen note present

## Feature verification matrix (headless backend probe, after env fix)

- One-button update/reconcile: `/api/updates/*` — WORKS ("Your customized versions were preserved.")
- Live-layer read path: `/api/curriculum/overview`, `/api/teacher/lens` — WORKS
- Google Drive: 9 routes up, `configured:false` graceful — needs OAuth creds for round-trip
- Slack ops v1+v2: `/api/slack/*`, `/api/ops/*` — up, graceful unconfigured — needs tokens for live bot
- Sources/filemap: `/api/extraction/sources`, `/api/filemap/*` — WORKS
- School ethos: loads; `/api/admin/evidence` = `status:"deferred"` (Phase 7 dashboard not built)
- Core: 111 ontology nodes / 178 knowledge / 559 citations; Ollama reachable

## Secondary notes

1. `/api/health` runs the full `run_doctor` dev audit and returns `status:"BLOCKED"` — non-fatal, but a readiness probe shouldn't run a governance self-audit.
2. The `.app` inside the DMG is NOT stapled — only the DMG is; offline first-launch after drag-to-/Applications may still contact Apple.
3. Linux download button points to `releases/latest/download/lv-linux-x86_64` (CLI v1.0.6, ~12 commits behind HEAD), not LinguaViva.AppImage.
4. Admin Evidence dashboard deferred — expected.

## Priority (from the report)

1. LV-5 (CRITICAL) — fix 3 add_event_handler calls + pin installer deps + boot smoke test → ship desktop-v0.2.12. **[DONE, this commit]**
2. Staple the `.app` (not just the DMG). **[deferred]**
3. Fix the Linux button artifact. **[deferred — operator decision]**
4. Make `/api/health` a lightweight liveness probe. **[deferred]**
