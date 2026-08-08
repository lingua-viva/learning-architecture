from __future__ import annotations

import re
from pathlib import Path

from src.lingua_viva.runtime_paths import memory_data_dir, runtime_data_dir


RUNTIME_DIRS = ("src", "sanitizer", "doctor", "runtime", "desktop", "memory", "agents", "skills")
FORBIDDEN_PATTERNS = (
    'Path(__file__).parent / "data"',
    "Path(__file__).parent / 'data'",
)
# Class pattern: any write-location default derived from __file__ that reaches a
# "data" directory, including chained ``.parent`` walks into ``memory/data``.
FORBIDDEN_RE = re.compile(
    r"Path\(__file__\)(?:\.parent)+\s*/\s*(?:['\"]memory['\"]\s*/\s*)?['\"]data['\"]"
)


def test_runtime_data_dir_uses_state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))

    path = runtime_data_dir("sanitizer")

    assert path == tmp_path / "state" / "runtime" / "sanitizer"
    assert path.is_dir()


def test_memory_data_dir_uses_state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))

    path = memory_data_dir()

    assert path == tmp_path / "state" / "runtime" / "memory"
    assert path.is_dir()


def test_runtime_modules_do_not_default_writes_to_source_tree():
    repo = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for dirname in RUNTIME_DIRS:
        root = repo / dirname
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if "release" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in text:
                    offenders.append(f"{path.relative_to(repo)}: {pattern}")
            for match in FORBIDDEN_RE.finditer(text):
                offenders.append(f"{path.relative_to(repo)}: {match.group(0)}")
    assert offenders == []
