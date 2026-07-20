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

import pytest


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
    # assertions (student_lenses.db and the dev revision log are
    # intentionally stable in production — the revision log in
    # particular is a real, partly-committed dev audit trail, not per-user
    # scratch state, so its default location must not change). Tests still
    # need their own isolated copies.
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(state_home / "student_lenses.db"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(state_home / "lv_revision_log.ndjson"))

    # (c) Ingest temp dir — see web._ingest_temp_dir()'s LV_INGEST_TMP_DIR
    # override (MC-lessons §1c).
    monkeypatch.setenv("LV_INGEST_TMP_DIR", str(state_home / "ingest-tmp"))

    # Request-outcome event log (MC-lessons §5).
    monkeypatch.setenv("LV_REQUEST_LOG_PATH", str(state_home / "request_events.ndjson"))

    # sanitizer/app.py's DATA_DIR defaults to the tracked sanitizer/data/
    # directory unless frozen — every test that touches the sanitizer was
    # appending real firewall_log.ndjson lines to the repo tree. Found during
    # the §9 desktop-build dirty-tree check (MC-lessons §1 gap, same class as
    # the original ingest-tmp finding).
    monkeypatch.setenv("LV_SANITIZER_DATA_DIR", str(state_home / "sanitizer-data"))
