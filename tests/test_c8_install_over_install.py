"""C8 — install-over-install keeps every lens (U1 Rung 2 lock; readiness path day 3).

The promise: a teacher who updates Lingua Viva keeps every student lens she had.
What makes it true today, and what each test pins:

  1. The store lives under the STATE home (~/.lingua-viva/runtime/student_lenses.db),
     never inside the app tree the installer replaces.            -> test_state_home_*
  2. The next release's code opens the previous release's store without losing a row:
     schema is CREATE IF NOT EXISTS + additive ALTERs.             -> test_shipped_store_*
  3. No installer, bootstrap or uninstaller deletes the state home. -> test_installers_*
  4. The migration code stays additive.                            -> test_schema_*

The fixture tests/fixtures/c8/student_lenses_v0.2.84.sql is a store as the
shipped release writes it (scripts/make_c8_fixture.py documents provenance).
Never edit it; add a new one per frozen release.

What this file cannot prove: the packaged installer on a real machine. That is
Mical's live cycle (plan #3 "Done means") — this file makes the failure classes
detectable before he spends a cycle on them.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.education.student_lens import StudentLensStore  # noqa: E402
from src.lingua_viva import config as lv_config  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "c8" / "student_lenses_v0.2.84.sql"
TABLES = ("students", "observations", "rti_decisions", "evidence_records", "teacher_roster")


def _restore(sql_path: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(sql_path.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def _counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    out = {}
    for t in TABLES:
        try:
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = -1  # table missing
    conn.close()
    return out


def _rows(db_path: Path, table: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
    conn.close()
    return rows


# --- 2. the shipped store survives this code ---------------------------------

def test_shipped_store_opens_with_this_code_and_keeps_every_row(tmp_path):
    db = tmp_path / "runtime" / "student_lenses.db"
    _restore(FIXTURE, db)
    before = _counts(db)
    assert before["students"] == 6, before
    assert all(v >= 0 for v in before.values()), before
    students_before = _rows(db, "students")
    observations_before = _rows(db, "observations")

    store = StudentLensStore(db_path=db)      # the "update": new code opens the old file
    try:
        after = _counts(db)
        assert after == before, f"opening the store changed row counts: {before} -> {after}"

        lenses = store.list_lenses()
        names = sorted(l["display_name"] for l in lenses)
        assert names == sorted([
            "Lucà Rossi", "Noëmi Villa", "Chang Abigail", "Chang Marco",
            "Bianchi Sofia", "Giuseppe Esposito",
        ]), names   # accents intact — the U1 click path's step 5 promise

        for lens in lenses:
            full = store.export_lens(lens["student_id"])
            assert full["display_name"] == lens["display_name"]
            assert full.get("deleted") in (False, 0, None)

        # every kind of row is still readable through the API, not just counted
        luca = store.export_lens("s-luca-rossi")
        assert luca["cefr_snapshot"].get("reading") == "A2", luca["cefr_snapshot"]
        noemi = store.export_lens("s-noemi-villa")
        assert noemi["cefr_snapshot"].get("speaking") == "A2+", noemi["cefr_snapshot"]
        abigail = store.get_support_profile("s-chang-abigail")
        texts = [e["text"] for e in abigail["categories"]["learning_and_cognition"]["strengths"]]
        assert "Works independently and finishes early" in texts, texts
        assert store.list_evidence(student_id="s-giuseppe-esposito"), "evidence ledger lost"
        assert store.list_lenses_for_teacher("teacher-fixture"), "teacher roster lost"
    finally:
        store.close()

    # the ORIGINAL rows are byte-identical after the migration ran (additive ALTERs may
    # add columns; they must not rewrite what was there)
    def _prefix(rows, n):
        return [r[:n] for r in rows]
    assert _prefix(_rows(db, "students"), len(students_before[0])) == students_before
    assert _prefix(_rows(db, "observations"), len(observations_before[0])) == observations_before


def test_opening_twice_is_idempotent(tmp_path):
    """Second launch after the update: the migration must not run destructively again."""
    db = tmp_path / "runtime" / "student_lenses.db"
    _restore(FIXTURE, db)
    StudentLensStore(db_path=db).close()
    once = _counts(db)
    StudentLensStore(db_path=db).close()
    assert _counts(db) == once


# --- 1. the state home is outside the install tree ---------------------------

def test_state_home_defaults_under_the_user_home_not_the_app_tree(monkeypatch, tmp_path):
    monkeypatch.delenv("LV_CONFIG_HOME", raising=False)
    monkeypatch.delenv("SIR_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    home = lv_config.lv_home()
    assert home == tmp_path / "home" / ".lingua-viva"
    assert REPO not in home.parents and home != REPO, "state must never live inside the checkout the installer replaces"
    assert Path(sys.prefix) not in home.parents, "state must never live inside the interpreter/venv"


def test_state_home_honours_the_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "elsewhere"))
    assert lv_config.lv_home() == tmp_path / "elsewhere"


def test_desktop_backend_inherits_the_home_and_does_not_point_state_into_the_bundle():
    src = (REPO / "desktop" / "electron" / "bootstrap.ts").read_text(encoding="utf-8")
    assert 'path.join(os.homedir(), ".lingua-viva")' in src, "desktop stateDir() must be under the user's home"
    m = re.search(r"const backendEnv[^;]*?\{(.*?)\};", src, re.S)
    assert m, "backendEnv block not found"
    assert "LV_CONFIG_HOME" not in m.group(1) and "SIR_CONFIG_HOME" not in m.group(1), (
        "the desktop must not redirect the backend's state into the bundle: " + m.group(1)
    )


# --- 3. nothing deletes the state home ----------------------------------------

_DELETE_RE = re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+\"?\$\{?HOME\}?/\.lingua-viva\"?\s*(?:$|;|&&|\|\|)", re.M)


def test_installers_never_delete_the_state_home():
    sh = (REPO / "install.sh").read_text(encoding="utf-8")
    assert not _DELETE_RE.search(sh), "install.sh removes ~/.lingua-viva (the teacher's lenses live there)"
    # the source-fallback path may `git pull` into an existing home (keeps untracked runtime/)
    # or refuse to clone into a non-empty one — both keep the store; a wipe would not
    assert "git pull" in sh and "git clone" in sh

    for name in ("bootstrap.ts", "main.ts"):
        ts = (REPO / "desktop" / "electron" / name).read_text(encoding="utf-8")
        for call in re.finditer(r"\b(rmSync|rm|rmdirSync|rmdir|removeSync)\s*\(([^)]*)\)", ts):
            arg = call.group(2)
            assert "stateDir()" not in arg and ".lingua-viva" not in arg and "homedir()" not in arg, (
                f"desktop/electron/{name} deletes under the state home: {call.group(0)}"
            )


def test_windows_uninstaller_keeps_app_data():
    pkg = json.loads((REPO / "desktop" / "package.json").read_text(encoding="utf-8"))
    nsis = (pkg.get("build") or {}).get("nsis") or {}
    assert nsis.get("deleteAppDataOnUninstall") is not True, "uninstall must not wipe the teacher's data"


# --- 4. migration stays additive ----------------------------------------------

def test_schema_migration_is_additive_only():
    src = (REPO / "src" / "education" / "student_lens.py").read_text(encoding="utf-8")
    assert not re.search(r"DROP\s+(TABLE|COLUMN)", src, re.I), "schema code drops — lenses would not survive an update"
    assert not re.search(r"CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)", src, re.I), "CREATE TABLE without IF NOT EXISTS"
    # the only row deletion of a student is the explicit hard delete
    deletes = [m.start() for m in re.finditer(r"DELETE\s+FROM\s+students", src)]
    assert len(deletes) == 1, deletes
    hard_delete_at = src.index("def delete_lens(")
    assert deletes[0] > hard_delete_at, "a student delete outside delete_lens()"
