from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


EDUCATION_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "curriculum": [
        "curriculum", "lesson", "unit", "syllabus", "programme", "indicazioni",
        "manuale", "piano", "programmazione", "scope", "sequence", "scheme",
    ],
    "assessment": [
        "assessment", "rubric", "portfolio", "grade", "valutazione", "test",
        "exam", "evaluation", "checklist", "criteria",
    ],
    "cefr": [
        "cefr", "a1", "a2", "b1", "b2", "proficiency", "level", "can-do",
        "competenza", "livello",
    ],
    "resources": [
        "resource", "material", "worksheet", "activity", "risorsa", "scheda",
        "attività", "template",
    ],
    "reference": [
        "reference", "research", "article", "framework", "ib", "pyp",
        "reggio", "montessori",
    ],
    "planning": [
        "plan", "planning", "weekly", "daily", "schedule", "timetable",
        "calendar", "orario",
    ],
}

STUDENT_DATA_KEYWORDS: list[str] = [
    "student", "studente", "alunno", "pupil",
    "iep", "bes", "pdp",
    "observation", "osservazione",
    "report", "pagella", "scheda-valutazione",
    "parent", "genitore", "famiglia",
    "confidential", "riservato", "private",
    "grade-book", "registro",
]

SENSITIVITY_KEYWORDS: dict[str, list[str]] = {
    "high": STUDENT_DATA_KEYWORDS + [
        "medical", "health", "salute", "credential", "password", "secret", "token",
    ],
    "medium": ["draft", "bozza", "internal", "interno", "review"],
}

SKIP_DIRS: set[str] = {
    ".git", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".cache", ".tmp", ".Trash",
}

PRIVACY_PATH_MARKERS: tuple[str, ...] = (
    "student_lens", "observations", "parent_reports", "progress_reports",
    "iep", "private",
)


@dataclass
class FileMapEntry:
    path: str
    file_count: int
    total_size_bytes: int
    last_modified: str
    inferred_domain: Optional[str] = None
    sensitivity: str = "low"
    depth: int = 0


@dataclass
class ScanRoot:
    path: str
    scanned_at: str
    entry_count: int = 0
    domain_summary: dict[str, int] = field(default_factory=dict)
    student_zones_detected: int = 0


@dataclass
class FileMap:
    roots: list[ScanRoot] = field(default_factory=list)
    entries: list[FileMapEntry] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    student_zones: list[str] = field(default_factory=list)
    version: int = 1


def storage_path() -> Path:
    override = os.environ.get("LV_FILE_MAP_PATH")
    if override:
        return Path(override).expanduser()
    from src.lingua_viva.config import lv_home
    return lv_home() / "file_map.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normal(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def display_path(path: str | Path) -> str:
    path_text = str(path)
    home = str(Path.home())
    if path_text == home:
        return "~"
    if path_text.startswith(home + os.sep):
        return "~" + path_text[len(home):]
    return path_text


def _path_from_storage(path: str) -> str:
    if path == "~":
        return str(Path.home())
    if path.startswith("~/"):
        return str(Path.home() / path[2:])
    return path


def infer_education_domain(dir_path: str | Path) -> Optional[str]:
    path_lower = str(dir_path).lower()
    for domain, keywords in EDUCATION_DOMAIN_KEYWORDS.items():
        if any(keyword in path_lower for keyword in keywords):
            return domain
    return None


def infer_sensitivity(dir_path: str | Path) -> str:
    path_lower = str(dir_path).lower()
    if any(keyword in path_lower for keyword in SENSITIVITY_KEYWORDS["high"]):
        return "high"
    if any(keyword in path_lower for keyword in SENSITIVITY_KEYWORDS["medium"]):
        return "medium"
    return "low"


def is_student_data_zone(dir_path: str | Path) -> bool:
    path_lower = str(dir_path).lower()
    return any(keyword in path_lower for keyword in STUDENT_DATA_KEYWORDS)


def _is_excluded(path: Path, exclusions: list[str]) -> bool:
    for exclusion in exclusions:
        try:
            excluded = _normal(exclusion)
        except OSError:
            continue
        if path == excluded or _is_relative_to(path, excluded):
            return True
    return False


def scan_directory(root: str | Path, max_depth: int = 3, exclusions: list[str] | None = None) -> list[FileMapEntry]:
    entries, _student_zones = _scan_directory(root, max_depth=max_depth, exclusions=exclusions)
    return entries


def _scan_directory(
    root: str | Path,
    max_depth: int = 3,
    exclusions: list[str] | None = None,
) -> tuple[list[FileMapEntry], list[str]]:
    root_path = _normal(root)
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Scan root must be an existing directory: {root}")

    exclusions = exclusions or []
    entries: list[FileMapEntry] = []
    student_zones: list[str] = []

    for current, dirs, files in os.walk(root_path, topdown=True, followlinks=False):
        current_path = Path(current)
        try:
            depth = len(current_path.relative_to(root_path).parts)
        except ValueError:
            continue

        dirs[:] = [
            name for name in dirs
            if name not in SKIP_DIRS
            and not name.startswith(".")
            and not (current_path / name).is_symlink()
        ]

        kept_dirs = []
        for name in dirs:
            child = current_path / name
            child_text = str(child).lower()
            if _is_excluded(child, exclusions) or is_student_data_zone(child) or any(marker in child_text for marker in PRIVACY_PATH_MARKERS):
                student_zones.append(str(child))
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs

        if depth > max_depth:
            dirs[:] = []
            continue
        if _is_excluded(current_path, exclusions) or is_student_data_zone(current_path):
            dirs[:] = []
            student_zones.append(str(current_path))
            continue

        file_count = 0
        total_size = 0
        last_modified = 0.0
        for name in files:
            file_path = current_path / name
            if file_path.is_symlink():
                continue
            try:
                stat = os.stat(file_path)
            except OSError:
                continue
            file_count += 1
            total_size += stat.st_size
            last_modified = max(last_modified, stat.st_mtime)

        try:
            dir_stat = os.stat(current_path)
            last_modified = max(last_modified, dir_stat.st_mtime)
        except OSError:
            pass

        entries.append(FileMapEntry(
            path=str(current_path),
            file_count=file_count,
            total_size_bytes=total_size,
            last_modified=datetime.fromtimestamp(last_modified or 0, timezone.utc).isoformat(),
            inferred_domain=infer_education_domain(current_path),
            sensitivity=infer_sensitivity(current_path),
            depth=depth,
        ))

    return entries, sorted(set(student_zones))


def load_map() -> FileMap:
    path = storage_path()
    if not path.exists():
        return FileMap()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return FileMap()
    return FileMap(
        roots=[ScanRoot(**item) for item in data.get("roots", [])],
        entries=[FileMapEntry(**item) for item in data.get("entries", [])],
        exclusions=[_path_from_storage(str(item)) for item in data.get("exclusions", [])],
        student_zones=[_path_from_storage(str(item)) for item in data.get("student_zones", [])],
        version=int(data.get("version", 1)),
    )


def save_map(file_map: FileMap) -> None:
    path = storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(file_map)
    data["exclusions"] = [display_path(item) for item in file_map.exclusions]
    data["student_zones"] = [display_path(item) for item in file_map.student_zones]
    for root in data["roots"]:
        root["path"] = display_path(root["path"])
    for entry in data["entries"]:
        entry["path"] = display_path(entry["path"])
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    os.chmod(path, 0o600)


def clear_map() -> None:
    try:
        storage_path().unlink()
    except FileNotFoundError:
        return


def run_scan(root_path: str | Path, max_depth: int = 3) -> FileMap:
    existing = load_map()
    root = _normal(root_path)
    entries, student_zones = _scan_directory(root, max_depth=max_depth, exclusions=existing.exclusions)
    existing.entries = [
        entry for entry in existing.entries
        if not (Path(_path_from_storage(entry.path)) == root or _is_relative_to(Path(_path_from_storage(entry.path)), root))
    ] + entries
    existing.student_zones = sorted(set(existing.student_zones + student_zones))

    domain_summary: dict[str, int] = {}
    for entry in entries:
        if entry.inferred_domain:
            domain_summary[entry.inferred_domain] = domain_summary.get(entry.inferred_domain, 0) + 1
    existing.roots = [
        scan_root for scan_root in existing.roots
        if _normal(_path_from_storage(scan_root.path)) != root
    ]
    existing.roots.append(ScanRoot(
        path=str(root),
        scanned_at=_now(),
        entry_count=len(entries),
        domain_summary=domain_summary,
        student_zones_detected=len(student_zones),
    ))
    save_map(existing)
    return existing


def add_exclusion(path: str | Path) -> FileMap:
    file_map = load_map()
    exclusion = str(_normal(path))
    if exclusion not in file_map.exclusions:
        file_map.exclusions.append(exclusion)
    file_map.entries = [
        entry for entry in file_map.entries
        if not _is_relative_to(_normal(_path_from_storage(entry.path)), Path(exclusion))
        and _normal(_path_from_storage(entry.path)) != Path(exclusion)
    ]
    save_map(file_map)
    return file_map


def remove_exclusion(path: str | Path) -> FileMap:
    file_map = load_map()
    target = str(_normal(path))
    file_map.exclusions = [item for item in file_map.exclusions if str(_normal(item)) != target]
    save_map(file_map)
    return file_map


def summarize(file_map: FileMap) -> dict:
    domains: dict[str, int] = {}
    for entry in file_map.entries:
        if entry.inferred_domain:
            domains[entry.inferred_domain] = domains.get(entry.inferred_domain, 0) + 1
    return {
        "configured": bool(file_map.roots or file_map.entries),
        "root_count": len(file_map.roots),
        "total_directories": len(file_map.entries),
        "domains_detected": domains,
        "student_zones_excluded": len(file_map.student_zones),
    }


def to_api(file_map: FileMap) -> dict:
    return {
        "version": file_map.version,
        "roots": [
            {
                **asdict(root),
                "path": display_path(root.path),
            }
            for root in file_map.roots
        ],
        "entries": [
            {
                **asdict(entry),
                "path": display_path(entry.path),
            }
            for entry in file_map.entries
        ],
        "exclusions": [display_path(path) for path in file_map.exclusions],
        "student_zones_detected": len(file_map.student_zones),
        "summary": summarize(file_map),
    }


def build_filemap_context(query_domain: Optional[str], *, local_only: bool = True) -> str:
    if not local_only or not query_domain:
        return ""
    file_map = load_map()
    matching = [
        entry for entry in file_map.entries
        if entry.inferred_domain == query_domain and entry.sensitivity != "high"
    ]
    if not matching:
        return ""
    lines = [f"Teacher has {len(matching)} {query_domain} folders:"]
    for entry in matching[:5]:
        lines.append(f"  - {display_path(entry.path)} ({entry.file_count} files)")
    return "\n".join(lines)
