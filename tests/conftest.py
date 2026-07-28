"""
Suite-wide test hermeticity (MC-lessons §1, 2026-07-19).

Mission Canvas's own `tests/conftest.py` autouse `_hermetic_governance`
fixture is why MC's app-improvement sweep dirty-state audit came back
clean. Lingua Viva had no `tests/conftest.py` at all — the final-polish
report's stale `ingest-tmp/tmp*.pdf` files under case-studies/ were a
symptom of that gap, patched at the instance level (one glob-and-delete in
`web._ingest_temp_dir()`) rather than the class level. This fixture is the
class-level fix: every test gets its own `~/.lingua-viva/`-equivalent state
home under `tmp_path`, so no test can read or write the operator's real
local state, and no test can dirty a tracked file in the repo tree
(observations, `dev/lv_revision_log.ndjson`, ingest scratch files, ...).

Individual tests that need a *specific* path (e.g. to assert on file
contents) still call `monkeypatch.setenv("LV_TRACE_PATH", ...)` themselves
— that assignment runs after this fixture's setup and simply overrides it,
same pattern as MC's own fixture.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _hermetic_lv_state(monkeypatch, tmp_path):
    # (b) Clear any LV_* env vars a test didn't explicitly set itself, so
    # no test can inherit stray state from the invoking shell.
    for key in list(os.environ):
        if key.startswith("LV_") or key.startswith("SIR_"):
            monkeypatch.delenv(key, raising=False)

    state_home = tmp_path / ".hermetic-lv-state"
    state_home.mkdir()

    # (a) Canonical seam: config.lv_home() (== config_home()) is consulted
    # by traces.py, privacy_log.py, and filemap.py whenever their own
    # specific override isn't set — that's what makes it "one seam", not
    # N hardcoded Path.home() calls. We still set the three specific
    # overrides directly here rather than LV_CONFIG_HOME itself, because
    # config_home() is shared with provider_config.py; several focused tests
    # set LV_CONFIG_HOME themselves. Forcing LV_CONFIG_HOME here would win
    # config_home()'s precedence check and silently break that isolation.
    monkeypatch.setenv("LV_TRACE_PATH", str(state_home / "traces.ndjson"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(state_home / "privacy_events.ndjson"))
    monkeypatch.setenv("LV_FILE_MAP_PATH", str(state_home / "file_map.yaml"))

    # Specific overrides for state paths whose tests need direct file
    # assertions. The runtime revision log's default moved to
    # lv_home()/dev/ in SPEC_ONE_BUTTON_UPDATE_2026-07-27 P0 (teacher
    # reflections were being appended inside the updater-owned bundle);
    # the *committed* dev/lv_revision_log.ndjson in the repo remains the
    # authoring audit trail that doctor checks. Tests still need their
    # own isolated copies.
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(state_home / "student_lenses.db"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(state_home / "lv_revision_log.ndjson"))

    # One-button-update state (SPEC_ONE_BUTTON_UPDATE_2026-07-27): the
    # reconcile manifest/templates/pending/archive tree defaults to
    # lv_home(), which in tests is the operator's REAL ~/.lingua-viva
    # (LV_CONFIG_HOME is deliberately not forced here — see (a) above).
    # Without this override, any test that runs app startup would
    # reconcile templates into the operator's real home.
    monkeypatch.setenv("LV_UPDATE_HOME", str(state_home / "update-home"))

    # (c) Ingest temp dir — see web._ingest_temp_dir()'s LV_INGEST_TMP_DIR
    # override (MC-lessons §1c).
    monkeypatch.setenv("LV_INGEST_TMP_DIR", str(state_home / "ingest-tmp"))

    # Request-outcome event log (MC-lessons §5).
    monkeypatch.setenv("LV_REQUEST_LOG_PATH", str(state_home / "request_events.ndjson"))

    # extraction_sources' demo-file fallback (web.py) writes into
    # lv_home()/imports/ when no sources exist — under tests that was the
    # operator's REAL ~/.lingua-viva/imports/ (found in the 2026-07-27 Drive
    # hardening loop; same class as the sanitizer gap above).
    monkeypatch.setenv("LV_LOCAL_IMPORTS_DIR", str(state_home / "local-imports"))

    # sanitizer/app.py's DATA_DIR defaults to the tracked sanitizer/data/
    # directory unless frozen — every test that touches the sanitizer was
    # appending real firewall_log.ndjson lines to the repo tree. Found during
    # the §9 desktop-build dirty-tree check (MC-lessons §1 gap, same class as
    # the original ingest-tmp finding).
    monkeypatch.setenv("LV_SANITIZER_DATA_DIR", str(state_home / "sanitizer-data"))

    # Slack ops assistant (SPEC_LV_SLACK_OPS_ASSISTANT_2026-07-27 Lane C):
    # ops record DB, daily-file output dir, and the daily-reset marker.
    # Without these, ops_records/daily_file default resolution could write
    # "Today - *.md" onto the operator's REAL Desktop (or ~/.lingua-viva/
    # ops/) from a test — same class of gap as the sanitizer finding above.
    monkeypatch.setenv("LV_OPS_DB_PATH", str(state_home / "ops_records.db"))
    monkeypatch.setenv("LV_OPS_DESKTOP_DIR", str(state_home / "ops-desktop"))
    monkeypatch.setenv("LV_OPS_STATE_PATH", str(state_home / "ops_state.json"))

    # In-app Google sign-in (SPEC_LV_DRIVE_SELF_SERVICE_AUTH_2026-07-27 §A):
    # stored auth defaults to lv_home()/config/google_drive.json — the
    # operator's REAL sign-in on this machine. Without this override, any
    # test touching drive status/settings would read (or worse, a disconnect
    # test would DELETE) the operator's real refresh token.
    monkeypatch.setenv("LV_GOOGLE_DRIVE_AUTH_PATH", str(state_home / "google_drive.json"))
    # status() now consults the connected-folders registry for can_upload
    # (§A5) — default path is the operator's REAL lv_home()/runtime/.
    monkeypatch.setenv("LV_GOOGLE_DRIVE_FOLDERS_PATH", str(state_home / "drive_folders.json"))
