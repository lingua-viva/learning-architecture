from __future__ import annotations

import os
import sys
import threading
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
    confirmations: dict[str, str] = field(default_factory=dict)
    student_assignments: list[dict] = field(default_factory=list)
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
    if path.startswith("~/") or path.startswith("~\\"):
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
        confirmations={
            _path_from_storage(str(key)): str(value)
            for key, value in (data.get("confirmations") or {}).items()
        },
        student_assignments=[
            {
                **item,
                "file_path": _path_from_storage(str(item["file_path"])),
            }
            for item in (data.get("student_assignments") or [])
            if isinstance(item, dict) and item.get("file_path")
        ],
        version=int(data.get("version", 1)),
    )


def save_map(file_map: FileMap) -> None:
    path = storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(file_map)
    data["exclusions"] = [display_path(item) for item in file_map.exclusions]
    data["student_zones"] = [display_path(item) for item in file_map.student_zones]
    data["confirmations"] = {
        display_path(path): purpose
        for path, purpose in file_map.confirmations.items()
    }
    data["student_assignments"] = [
        {
            **assignment,
            "file_path": display_path(assignment["file_path"]),
        }
        for assignment in file_map.student_assignments
    ]
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
    valid_entry_paths = {
        str(_normal(_path_from_storage(entry.path)))
        for entry in existing.entries
    }
    existing.confirmations = {
        path: purpose
        for path, purpose in existing.confirmations.items()
        if str(_normal(_path_from_storage(path))) in valid_entry_paths
    }
    retained_zones = [
        zone for zone in existing.student_zones
        if not (
            _normal(_path_from_storage(zone)) == root
            or _is_relative_to(_normal(_path_from_storage(zone)), root)
        )
    ]
    existing.student_zones = sorted(set(retained_zones + student_zones))
    known_zone_paths = {
        str(_normal(_path_from_storage(zone)))
        for zone in existing.student_zones
    }
    existing.student_assignments = [
        assignment for assignment in existing.student_assignments
        if str(_normal(_path_from_storage(assignment["file_path"])).parent) in known_zone_paths
    ]

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
    valid_entry_paths = {
        str(_normal(_path_from_storage(entry.path)))
        for entry in file_map.entries
    }
    file_map.confirmations = {
        path: purpose
        for path, purpose in file_map.confirmations.items()
        if str(_normal(_path_from_storage(path))) in valid_entry_paths
    }
    file_map.student_zones = [
        zone for zone in file_map.student_zones
        if not (
            _normal(_path_from_storage(zone)) == Path(exclusion)
            or _is_relative_to(_normal(_path_from_storage(zone)), Path(exclusion))
        )
    ]
    known_zone_paths = {
        str(_normal(_path_from_storage(zone)))
        for zone in file_map.student_zones
    }
    file_map.student_assignments = [
        assignment for assignment in file_map.student_assignments
        if str(_normal(_path_from_storage(assignment["file_path"])).parent) in known_zone_paths
    ]
    save_map(file_map)
    return file_map


def remove_exclusion(path: str | Path) -> FileMap:
    file_map = load_map()
    target = str(_normal(path))
    file_map.exclusions = [item for item in file_map.exclusions if str(_normal(item)) != target]
    save_map(file_map)
    return file_map


def confirm_entry(path: str | Path, purpose: str) -> FileMap:
    if purpose not in {"curriculum_source", "ignore"}:
        raise ValueError("purpose must be curriculum_source or ignore")
    file_map = load_map()
    target = _normal(_path_from_storage(str(path)))
    known_paths = {
        _normal(_path_from_storage(entry.path))
        for entry in file_map.entries
    }
    if target not in known_paths:
        raise ValueError("path is not an entry in the current file map")
    file_map.confirmations[str(target)] = purpose
    save_map(file_map)
    return file_map


def list_files_in_zone(zone_path: str | Path) -> list[dict]:
    """List one directory level using metadata only; never open file content."""
    zone_input = Path(_path_from_storage(str(zone_path))).expanduser()
    if zone_input.is_symlink():
        raise ValueError("Student zone cannot be a symbolic link")
    zone = zone_input.resolve()
    if not zone.exists() or not zone.is_dir():
        raise ValueError(f"Student zone must be an existing directory: {zone_path}")

    items: list[dict] = []
    with os.scandir(zone) as children:
        for child in children:
            if child.is_symlink():
                continue
            try:
                stat = child.stat(follow_symlinks=False)
            except OSError:
                continue
            items.append({
                "name": child.name,
                "path": str(zone / child.name),
                "type": "directory" if child.is_dir(follow_symlinks=False) else "file",
                "size_bytes": stat.st_size if child.is_file(follow_symlinks=False) else None,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            })
    return sorted(items, key=lambda item: (item["type"] != "directory", item["name"].lower()))


def assign_student_file(file_path: str | Path, assigned_student_id: str | None) -> FileMap:
    file_map = load_map()
    target = _normal(_path_from_storage(str(file_path)))
    known_zones = {
        _normal(_path_from_storage(zone))
        for zone in file_map.student_zones
    }
    if target.parent not in known_zones or not target.exists() or not target.is_file() or target.is_symlink():
        raise ValueError("file_path must be a direct file in a detected student zone")

    file_map.student_assignments = [
        item for item in file_map.student_assignments
        if _normal(_path_from_storage(str(item["file_path"]))) != target
    ]
    if assigned_student_id:
        file_map.student_assignments.append({
            "file_path": str(target),
            "assigned_student_id": assigned_student_id,
            "assigned_purpose": "student_lens_source",
        })
    save_map(file_map)
    return file_map


def record_imported_file_assignment(
    file_path: str | Path,
    assigned_purpose: str,
    assigned_student_id: str | None = None,
) -> FileMap:
    if assigned_purpose not in {
        "student_lens_source",
        "curriculum_unit_source",
        "teacher_artifact_source",
    }:
        raise ValueError("assigned_purpose is not supported for imported files")
    target = _normal(_path_from_storage(str(file_path)))
    if not target.exists() or not target.is_file() or target.is_symlink():
        raise ValueError("file_path must be an existing imported file")
    file_map = load_map()
    file_map.student_assignments = [
        item for item in file_map.student_assignments
        if _normal(_path_from_storage(str(item["file_path"]))) != target
    ]
    file_map.student_assignments.append({
        "file_path": str(target),
        "assigned_student_id": assigned_student_id,
        "assigned_purpose": assigned_purpose,
        "source": "google_drive_import",
    })
    save_map(file_map)
    return file_map


def get_confirmed_extraction_inputs(file_map: FileMap | None = None) -> list[dict]:
    mapped = file_map or load_map()
    schema_by_purpose = {
        "student_lens_source": "student_lens",
        "curriculum_unit_source": "curriculum_unit",
        "teacher_artifact_source": "teacher_artifact",
    }
    inputs = [
        {
            "file_path": str(_normal(_path_from_storage(assignment["file_path"]))),
            "target_schema_id": schema_by_purpose.get(
                assignment.get("assigned_purpose", "student_lens_source"),
                "student_lens",
            ),
            "hint": {
                "assigned_student_id": assignment.get("assigned_student_id"),
                "assigned_purpose": assignment.get("assigned_purpose", "student_lens_source"),
                **({"source": assignment["source"]} if assignment.get("source") else {}),
            },
        }
        for assignment in mapped.student_assignments
    ]
    for path, purpose in mapped.confirmations.items():
        if purpose != "curriculum_source":
            continue
        folder_input = Path(_path_from_storage(path)).expanduser()
        if folder_input.is_symlink():
            continue
        folder = folder_input.resolve()
        if not folder.is_dir():
            continue
        try:
            with os.scandir(folder) as children:
                files = [
                    child for child in children
                    if child.is_file(follow_symlinks=False) and not child.is_symlink()
                ]
        except OSError:
            continue
        inputs.extend({
            "file_path": str(folder / child.name),
            "target_schema_id": "curriculum_unit",
            "hint": {"confirmed_folder": str(folder)},
        } for child in sorted(files, key=lambda item: item.name.lower()))
    return inputs


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
        "confirmations": {
            display_path(path): purpose
            for path, purpose in file_map.confirmations.items()
        },
        "student_zones": [display_path(path) for path in file_map.student_zones],
        "student_zones_detected": len(file_map.student_zones),
        "student_assignments": [
            {
                **assignment,
                "file_path": display_path(assignment["file_path"]),
            }
            for assignment in file_map.student_assignments
        ],
        "confirmed_extraction_inputs": [
            {
                **item,
                "file_path": display_path(item["file_path"]),
                "hint": {
                    **item["hint"],
                    **(
                        {"confirmed_folder": display_path(item["hint"]["confirmed_folder"])}
                        if item["hint"].get("confirmed_folder")
                        else {}
                    ),
                },
            }
            for item in get_confirmed_extraction_inputs(file_map)
        ],
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


# --- Auto-scan on startup (Gap 2) ------------------------------------------
# SPEC_LV_REMAINING_GAPS_2026-07-29 Gap 2. The scan intelligence already
# existed — infer_education_domain(), is_student_data_zone(), the bilingual
# keyword lists. What was missing was the automatic trigger: nothing ran
# unless a teacher pressed a button, which makes "local-first" hollow.
#
# The spec says to port MC's auto_scan_on_startup(). That function does not
# exist in MC (src/filemap.py has no such symbol; the cited line 516 is inside
# generate_lens_claims), so this is written for LV's own shape rather than
# ported. LV's run_scan() already merges, prunes and saves, so the auto-scan
# only has to decide WHEN to call it.

AUTO_SCAN_THREAD_NAME = "lv-filemap-autoscan"

_scan_state_lock = threading.Lock()
_scan_in_progress = False


def is_scan_in_progress() -> bool:
    """True while an auto-scan is running. Safe to call from any thread."""
    with _scan_state_lock:
        return _scan_in_progress


def _set_scan_in_progress(value: bool) -> None:
    global _scan_in_progress
    with _scan_state_lock:
        _scan_in_progress = value


def auto_scan_disabled_reason() -> Optional[str]:
    """Why the auto-scan must not run, or None when it may.

    Two guards, and the second is not belt-and-braces — it is load-bearing.
    ``LV_AGENT=1`` is the documented convention (mirroring MC's ``MC_AGENT``),
    but a test that forgets to set it would otherwise scan the developer's
    real home directory: slow, and it would read personal files that have
    nothing to do with the test. Detecting pytest directly means the unsafe
    default cannot be reached by forgetting an env var.
    """
    if os.environ.get("LV_AGENT", "").strip() in {"1", "true", "yes", "on"}:
        return "LV_AGENT is set — agent and CI runs never scan the home folder."
    if "pytest" in sys.modules:
        return "running under pytest — the home folder is never scanned in tests."
    return None


def _scan_root_is_stale(scan_root: ScanRoot) -> bool:
    """True when a recorded root has changed since it was last scanned.

    Compares the directory's own mtime against the recorded scan time. A root
    that has vanished is NOT stale — re-scanning a missing path would only
    raise; it is left alone so the recorded entries survive an unplugged
    external drive rather than being silently deleted.
    """
    root = _normal(_path_from_storage(scan_root.path))
    try:
        if not root.is_dir():
            return False
        changed_at = root.stat().st_mtime
    except OSError:
        return False
    try:
        scanned_at = datetime.fromisoformat(scan_root.scanned_at).timestamp()
    except (ValueError, TypeError):
        return True  # unparseable timestamp — treat as stale and re-scan
    return changed_at > scanned_at


def roots_needing_rescan(file_map: Optional[FileMap] = None) -> list[ScanRoot]:
    current = file_map if file_map is not None else load_map()
    return [root for root in current.roots if _scan_root_is_stale(root)]


def auto_scan_on_startup(max_depth: int = 4) -> dict:
    """Populate or refresh the file map without the teacher asking.

    First launch (no recorded roots): scans the home folder. Later launches:
    re-scans only the roots whose directory mtime moved.

    Never raises. This runs on a daemon thread during startup, so a failure
    here must degrade to "no file map" rather than taking the teacher's app
    down with it. The returned dict says what happened, which is what the
    tests assert against and what a status route could surface.
    """
    blocked = auto_scan_disabled_reason()
    if blocked:
        return {"ran": False, "reason": blocked, "roots_scanned": []}

    if is_scan_in_progress():
        return {"ran": False, "reason": "a scan is already running.", "roots_scanned": []}

    _set_scan_in_progress(True)
    try:
        current = load_map()
        if not current.roots:
            targets = [Path.home()]
            trigger = "first launch"
        else:
            targets = [
                _normal(_path_from_storage(root.path))
                for root in roots_needing_rescan(current)
            ]
            trigger = "changed since last scan"

        if not targets:
            return {
                "ran": False,
                "reason": "every recorded folder is up to date.",
                "roots_scanned": [],
            }

        scanned: list[str] = []
        for target in targets:
            try:
                run_scan(target, max_depth=max_depth)
                scanned.append(display_path(target))
            except Exception:
                # One unreadable root must not abandon the others.
                continue

        return {"ran": bool(scanned), "reason": trigger, "roots_scanned": scanned}
    except Exception as exc:  # noqa: BLE001 - reported, never raised at startup
        return {"ran": False, "reason": f"scan failed ({type(exc).__name__})", "roots_scanned": []}
    finally:
        _set_scan_in_progress(False)
