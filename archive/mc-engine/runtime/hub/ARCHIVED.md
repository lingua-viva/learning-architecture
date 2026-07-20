# Archived: Mission Canvas voice hub (`runtime/hub/`)

Archived 2026-07-19 per `dev/specs/SPEC_APP_IMPROVEMENT_MC_LESSONS_2026-07-19.md` §4.

**Disposition: legacy, fork-era, not live.** Evidence:
- Only ever touched by the single fork-import commit `c2a9bf5 feat(engine):
  integrate Mission Canvas as governed AI engine` — never adapted to LV.
- Started only by `setup.sh`, itself a Mission Canvas launch script
  ("Mission Canvas — Setup & Launch") that references `src/api_server.py`
  and `src/mc_cli.py` — neither exists in this repo. `setup.sh` was already
  non-functional before this archival.
- Not referenced by `src/web.py`, `src/lingua_viva/`, the `lv` CLI, or
  `desktop/` — LV's actual runtime is `lv serve` (src/web.py, port 8787 by
  default), documented as the real entry point in `install.sh`.
- `runtime/hub/index.html` is a separate HTML surface from
  `static/index.html` (the real teacher UI) and has its own `sw.js`-free
  static assets — no cache-version parity risk with `static/sw.js`
  (`lv-pwa-v6`), since it was never a live PWA surface.

Kept for history alongside the rest of the archived MC engine machinery
(`archive/mc-engine/`). `runtime/broker/` was left in place (still
referenced by the archived `mc_cli.py` for history, out of §4's scope,
no live LV code path touches it either).
