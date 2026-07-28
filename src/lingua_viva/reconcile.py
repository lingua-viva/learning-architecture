"""One-button update — seed/live template reconcile.

SPEC_ONE_BUTTON_UPDATE_2026-07-27. Industry-consensus pattern (dpkg md5
database / RPM %config(noreplace) / pacman pacnew / OSTree /etc merge):
a hash manifest of every shipped artifact as-shipped, and a per-file
three-way compare (old-shipped vs on-disk vs new-shipped) on first launch
after an update.

Layers:
- **Seed layer**: shipped templates inside the app bundle / repo checkout
  (``seed_root()``). Read-only — the app never writes here.
- **Live layer**: ``update_home()/templates/<relative path>`` — the
  materialized working copies the teacher may edit.
- **Manifest**: ``update_home()/update_manifest.json`` — per managed
  artifact: canonicalized-content hash as shipped, shipping version,
  schema_version. Plus ``last_run_engine_version`` (downgrade stamp) and
  tombstone / renamed_from records.

THIS MODULE IS THE SOLE MANIFEST WRITER (dpkg sole-writer model — two
writers is research pitfall #3). The manifest write is the LAST operation
of any reconcile (OSTree single-commit-point), so a crash mid-reconcile
re-runs cleanly: per-file writes are temp+fsync+rename atomic and the
classification source of truth only advances once everything else landed.

Managed set (a deliberate decision, not "everything"): only
teacher-editable artifact classes are materialized and manifested —
``lenses/education/`` and ``curriculum/``. Engine-owned data
(``ontology/``, ``knowledge/``, ``src/``) stays bundle-only and updates
wholesale with the app; keeping it out of the managed set keeps the
reconcile fast and makes every conflict the surface shows a *meaningful*
teacher-vs-ship conflict. Extending the set is one tuple edit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import yaml

from .config import lv_home

MANIFEST_VERSION = 1
DEFAULT_SCHEMA_VERSION = 1

# Managed artifact classes — teacher-editable shipped templates only.
MANAGED_PREFIXES: tuple[str, ...] = (
    "lenses/education",
    "curriculum",
)

# Reserved namespace for shipped artifact IDs (research pitfall #4 — Anki
# numeric-ID lesson: solve collisions by construction at creation time).
RESERVED_ID_PREFIXES: tuple[str, ...] = ("lv-",)

# Ship-side removal/rename records (dpkg-maintscript-helper semantics).
# Versioned with the engine by definition; a release that removes or
# renames a managed template adds an entry here. Empty for now — the
# *mechanism* is the deliverable.
SHIPPED_TOMBSTONES: tuple[str, ...] = ()
SHIPPED_RENAMES: dict[str, str] = {}  # new relative path -> old relative path

# Per-schema-version migration hooks for USER-OWNED copies (HA
# ``_async_migrate_func`` pattern). Keyed on the schema_version being
# migrated FROM; each hook returns the artifact dict at version N+1.
# Identity today — the seam is the deliverable. Shipped seeds migrate at
# build time, never here.
SCHEMA_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


# --------------------------------------------------------------------------
# Path seams
# --------------------------------------------------------------------------

def seed_root() -> Path:
    """Root of the read-only shipped artifact tree (bundle or checkout)."""
    override = os.environ.get("LV_SEED_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2]


def update_home() -> Path:
    """Root of all mutable update state (manifest, live templates, pending,
    archive). Defaults to lv_home(); LV_UPDATE_HOME overrides (tests)."""
    override = os.environ.get("LV_UPDATE_HOME")
    if override:
        return Path(override)
    return lv_home()


def manifest_path() -> Path:
    return update_home() / "update_manifest.json"


def live_root() -> Path:
    return update_home() / "templates"


def pending_root() -> Path:
    return update_home() / "updates-pending"


def archive_root() -> Path:
    return update_home() / "archive"


def engine_version() -> str:
    """Single canonical engine-version source.

    Order: LV_ENGINE_VERSION env (tests / fake-update proof) →
    pyproject.toml at the seed root (source installs; not shipped in the
    desktop bundle) → ``src.lingua_viva.__version__`` (always shipped —
    kept in sync with pyproject as of this build)."""
    override = os.environ.get("LV_ENGINE_VERSION")
    if override:
        return override
    pyproject = seed_root() / "pyproject.toml"
    try:
        match = re.search(
            r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.MULTILINE
        )
        if match:
            return match.group(1)
    except OSError:
        pass
    from . import __version__

    return __version__


def _version_tuple(version: str) -> tuple:
    # Hardening iteration 11: "v1.0.7" parsed as (0,0,7) — a v-prefixed
    # version (easy mistake; release tags are desktop-v*) would trip the
    # downgrade guard and silently disable reconcile forever.
    text = str(version).strip().lstrip("vV")
    parts = []
    for chunk in text.split("."):
        digits = re.match(r"\d+", chunk)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


# --------------------------------------------------------------------------
# Hashing (canonicalized content — research pitfall #1)
# --------------------------------------------------------------------------

# The reconcile parses TEACHER-WRITABLE files. A 419-byte YAML alias bomb
# (billion laughs — safe_load expands anchors) measurably hangs the parse
# >15s, which would hang app startup forever (hardening iteration 1).
# Guard both directions: a size cap, and a loader that refuses aliases
# outright. Shipped templates use neither aliases nor >1MB files, so the
# fallback (raw-bytes hash) only ever errs toward false "modified" — a
# preserved file, never a destroyed one.
_MAX_PARSE_BYTES = 1_000_000


class _NoAliasLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):  # noqa: D102
        if self.check_event(yaml.events.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in managed templates")
        return super().compose_node(parent, index)


def _parse_yaml_guarded(raw: bytes):
    """safe_load with alias-expansion and size guards. Raises on anything
    suspicious — callers treat that as 'not canonicalizable' and fall back
    to raw bytes."""
    if len(raw) > _MAX_PARSE_BYTES:
        raise ValueError(f"file exceeds YAML parse cap ({len(raw)} bytes)")
    return yaml.load(raw.decode("utf-8"), Loader=_NoAliasLoader)


def canonical_hash(path: Path) -> str:
    """Hash canonicalized content, not raw bytes.

    A reformat (key reorder, quoting, trailing newline, CRLF) must NOT
    change the hash, or every pristine file misclassifies as "modified"
    and auto-update silently dies — the #1-ranked pitfall in
    RESEARCH_UPDATE_PRESERVATION_2026-07-27. YAML parses to plain types
    and re-serializes deterministically (sorted keys); anything that
    fails to parse (or trips the alias/size guards) falls back to a
    raw-bytes hash (the safe direction: false "modified", never false
    "unmodified")."""
    raw = path.read_bytes()
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            data = _parse_yaml_guarded(raw)
            canonical = json.dumps(
                data, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str
            )
            return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        except Exception:
            pass
    return hashlib.sha256(raw).hexdigest()


def _artifact_schema_version(path: Path) -> int:
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            data = _parse_yaml_guarded(path.read_bytes())
            if isinstance(data, dict):
                value = data.get("schema_version", DEFAULT_SCHEMA_VERSION)
                if isinstance(value, int):
                    return value
        except Exception:
            pass
    return DEFAULT_SCHEMA_VERSION


def managed_artifacts(root: Optional[Path] = None) -> list[str]:
    """Relative (POSIX-style) paths of every managed shipped artifact."""
    base = root or seed_root()
    found: list[str] = []
    for prefix in MANAGED_PREFIXES:
        directory = base / prefix
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.name.startswith("."):
                continue
            if path.suffix == ".py":
                continue  # engine code, even if it lives under a managed dir
            found.append(path.relative_to(base).as_posix())
    return found


# --------------------------------------------------------------------------
# Atomic writes + manifest IO
# --------------------------------------------------------------------------

def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """write-temp → fsync → rename (LWN canonical crash-safe write)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_manifest() -> Optional[dict]:
    try:
        data = json.loads(manifest_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _write_manifest(manifest: dict) -> None:
    """SOLE manifest write point. Always last in any reconcile pass."""
    manifest["manifest_version"] = MANIFEST_VERSION
    manifest["written_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_bytes(
        manifest_path(),
        (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8"),
    )


def _new_manifest(version: str) -> dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "last_run_engine_version": version,
        "artifacts": {},
        "pending": {},
        "tombstones": list(SHIPPED_TOMBSTONES),
        "renamed_from": dict(SHIPPED_RENAMES),
    }


# --------------------------------------------------------------------------
# Reconcile
# --------------------------------------------------------------------------

def _casefold_index(directory: Path) -> dict[str, Path]:
    """Case-folded relative-path index of the live layer (macOS/Windows are
    case-insensitive — research pitfall #10)."""
    index: dict[str, Path] = {}
    if not directory.is_dir():
        return index
    for path in directory.rglob("*"):
        if path.is_file() or path.is_symlink():
            index[path.relative_to(directory).as_posix().casefold()] = path
    return index


def _migrate_user_copy(rel: str, from_version: int, to_version: int) -> None:
    """Run registered schema migrations on a USER-OWNED live copy,
    stepwise from_version → to_version. Identity when no hooks are
    registered (the seam is the deliverable)."""
    if from_version >= to_version:
        return
    live_path = live_root() / rel
    if not live_path.is_file() or live_path.suffix.lower() not in (".yaml", ".yml"):
        return
    hooks = [SCHEMA_MIGRATIONS.get(v) for v in range(from_version, to_version)]
    if not any(hooks):
        return
    try:
        data = _parse_yaml_guarded(live_path.read_bytes())
    except Exception:
        return
    if not isinstance(data, dict):
        return
    for version, hook in zip(range(from_version, to_version), hooks):
        if hook is not None:
            data = hook(data)
        data["schema_version"] = version + 1
    _atomic_write_bytes(
        live_path,
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False).encode("utf-8"),
    )


def reconcile(force: bool = False) -> dict:
    """First-launch install-or-update reconcile. Idempotent; safe to
    re-run after a crash at any point (per-file atomic writes, manifest
    committed last). Returns a report dict; never raises for per-file
    trouble (a single bad artifact must not block the rest)."""
    current = engine_version()
    manifest = load_manifest()
    report: dict = {
        "ran": False,
        "fresh_install": False,
        "downgrade": False,
        "engine_version": current,
        "materialized": [],
        "upgraded": [],
        "preserved_modified": [],
        "staged_pending": [],
        "deleted_not_resurrected": [],
        "tombstoned": [],
        "renamed": [],
        "errors": [],
    }

    if manifest is None:
        report["ran"] = True
        report["fresh_install"] = True
        manifest = _new_manifest(current)
        _reconcile_pass(manifest, current, report)
        _write_manifest(manifest)  # LAST operation
        return report

    last_run = str(manifest.get("last_run_engine_version") or "0")
    if not force and last_run == current:
        return report  # fast no-op path — runs every launch

    if _version_tuple(last_run) > _version_tuple(current):
        # Downgrade guard (Firefox compatibility.ini model): warn-not-block,
        # read-only pass — no artifact writes, no manifest write.
        report["downgrade"] = True
        report["last_run_engine_version"] = last_run
        return report

    report["ran"] = True
    _reconcile_pass(manifest, current, report)
    manifest["last_run_engine_version"] = current
    _write_manifest(manifest)  # LAST operation
    return report


def _reconcile_pass(manifest: dict, current: str, report: dict) -> None:
    seed = seed_root()
    live = live_root()
    artifacts: dict = manifest.setdefault("artifacts", {})
    pending: dict = manifest.setdefault("pending", {})
    manifest.setdefault("tombstones", [])
    manifest.setdefault("renamed_from", {})
    live_index = _casefold_index(live)

    # Renames shipped with this release (mechanism; empty today): move an
    # UNMODIFIED live copy to its new name, mirror the manifest entry.
    for new_rel, old_rel in SHIPPED_RENAMES.items():
        entry = artifacts.get(old_rel)
        old_live = live / old_rel
        if entry and old_live.is_file() and not old_live.is_symlink():
            try:
                if canonical_hash(old_live) == entry.get("hash"):
                    target = live / new_rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(old_live, target)
                    artifacts[new_rel] = artifacts.pop(old_rel)
                    report["renamed"].append({"from": old_rel, "to": new_rel})
            except OSError as exc:
                report["errors"].append({"path": old_rel, "error": str(exc)})
        manifest["renamed_from"][new_rel] = old_rel

    # Tombstones (dpkg rm_conffile semantics): modified-check before delete.
    for rel in SHIPPED_TOMBSTONES:
        entry = artifacts.get(rel)
        live_path = live / rel
        if entry:
            if live_path.is_file() and not live_path.is_symlink():
                try:
                    if canonical_hash(live_path) == entry.get("hash"):
                        live_path.unlink()
                        report["tombstoned"].append(rel)
                    # modified → left alone (never destroy user work)
                except OSError as exc:
                    report["errors"].append({"path": rel, "error": str(exc)})
            artifacts.pop(rel, None)
            pending.pop(rel, None)
        if rel not in manifest["tombstones"]:
            manifest["tombstones"].append(rel)

    for rel in managed_artifacts(seed):
        try:
            _reconcile_one(rel, seed, live, live_index, artifacts, pending, current, report)
        except Exception as exc:  # noqa: BLE001 — docstring promise: one bad
            # artifact must never block the rest (hardening iteration 2:
            # OSError-only let a ValueError abort the whole pass — zero
            # files materialized on a fresh install).
            report["errors"].append({"path": rel, "error": str(exc)})


def _reconcile_one(
    rel: str,
    seed: Path,
    live: Path,
    live_index: dict[str, Path],
    artifacts: dict,
    pending: dict,
    current: str,
    report: dict,
) -> None:
    seed_path = seed / rel
    new_hash = canonical_hash(seed_path)
    schema_version = _artifact_schema_version(seed_path)
    live_path = live_index.get(rel.casefold(), live / rel)
    entry = artifacts.get(rel)

    def record() -> None:
        artifacts[rel] = {
            "hash": new_hash,
            "shipped_in": current,
            "schema_version": schema_version,
        }

    def stage_pending() -> None:
        staged = pending_root() / rel
        _atomic_write_bytes(staged, seed_path.read_bytes())
        pending[rel] = {
            "new_hash": new_hash,
            "shipped_in": current,
            "staged_path": str(staged),
        }
        report["staged_pending"].append(rel)

    if entry is None:
        # New shipped artifact (or fresh install).
        if live_path.exists() or live_path.is_symlink():
            # A file already sits at this (case-folded) path and the
            # manifest doesn't know it → user-created or user-modified.
            # Never touch it (all systems: unknown files are invisible to
            # the updater); ship the new version as pending instead.
            if not live_path.is_symlink() and live_path.is_file() and canonical_hash(live_path) == new_hash:
                record()
                return
            record()
            stage_pending()
            report["preserved_modified"].append(rel)
            return
        _atomic_write_bytes(live / rel, seed_path.read_bytes())
        record()
        report["materialized"].append(rel)
        return

    old_hash = entry.get("hash")
    old_schema = entry.get("schema_version", DEFAULT_SCHEMA_VERSION)

    if live_path.is_symlink():
        # Symlinks in the live layer are always user-modified — never touch.
        if new_hash != old_hash:
            stage_pending()
        record()
        report["preserved_modified"].append(rel)
        return

    if not live_path.exists():
        # User deleted it — deletion counts as modification; do NOT
        # resurrect (dpkg rule). Track the new ship so a future decision
        # is possible, but write nothing to the live layer.
        record()
        pending.pop(rel, None)
        report["deleted_not_resurrected"].append(rel)
        return

    live_hash = canonical_hash(live_path)

    if live_hash == old_hash:
        # Unmodified → silently upgrade (dpkg/RPM/pacman/OSTree unanimous).
        if new_hash != old_hash:
            _atomic_write_bytes(live_path, seed_path.read_bytes())
            report["upgraded"].append(rel)
        record()
        pending.pop(rel, None)
        _migrate_user_copy(rel, old_schema, schema_version)
        return

    if live_hash == new_hash:
        # User's edit already matches the new ship — nothing pending.
        record()
        pending.pop(rel, None)
        return

    # Modified → keep the user's file byte-identical; park the new
    # version as pending (RPM %config(noreplace) → .rpmnew).
    report["preserved_modified"].append(rel)
    if new_hash != old_hash:
        stage_pending()
    record()
    _migrate_user_copy(rel, old_schema, schema_version)


def reconcile_on_startup() -> dict:
    """Startup wrapper: run the reconcile, never raise."""
    try:
        return reconcile()
    except Exception as exc:  # startup must never take the app down
        return {"ran": False, "error": str(exc)}


# --------------------------------------------------------------------------
# Conflict surface (Phase 3) — pending review API
# --------------------------------------------------------------------------

def _is_safe_rel(rel: str) -> bool:
    """Defense-in-depth (hardening iteration 3): rels come from the
    manifest, which lives in teacher-writable space. A poisoned
    ``../../`` entry must never let resolve/diff read or write outside
    the managed roots — even though nothing writes such rels today."""
    if not rel or "\\" in rel:
        return False
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return False
    return any(rel == p or rel.startswith(p + "/") for p in MANAGED_PREFIXES)


def _pending_map(manifest: Optional[dict]) -> dict:
    """Tolerant accessor (hardening iteration 4): the manifest lives in
    teacher-writable space — corrupt shapes (non-dict pending, non-dict
    entries) must degrade to 'nothing pending', never a crash/500."""
    pending = (manifest or {}).get("pending")
    if not isinstance(pending, dict):
        return {}
    return {rel: entry for rel, entry in pending.items() if isinstance(entry, dict)}


def list_pending() -> list[dict]:
    pending = _pending_map(load_manifest())
    items = []
    for rel in sorted(pending):
        if not _is_safe_rel(rel):
            continue
        entry = pending[rel]
        items.append({
            "path": rel,
            "shipped_in": entry.get("shipped_in"),
            "staged_available": (pending_root() / rel).is_file(),
        })
    return items


def pending_count() -> int:
    return len(_pending_map(load_manifest()))


def downgrade_detected() -> Optional[dict]:
    """Non-None when the manifest was last written by a NEWER engine."""
    manifest = load_manifest()
    if not manifest:
        return None
    last_run = str(manifest.get("last_run_engine_version") or "0")
    current = engine_version()
    if _version_tuple(last_run) > _version_tuple(current):
        return {"last_run_engine_version": last_run, "engine_version": current}
    return None


def pending_diff(rel: str) -> Optional[str]:
    """Unified diff: teacher's live copy vs the staged new version."""
    import difflib

    manifest = load_manifest() or {}
    if not _is_safe_rel(rel) or rel not in _pending_map(manifest):
        return None
    staged = pending_root() / rel
    live_path = live_root() / rel
    if not staged.is_file():
        return None
    try:
        staged_lines = staged.read_text(encoding="utf-8").splitlines(keepends=True)
        live_lines = (
            live_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if live_path.is_file()
            else []
        )
    except (OSError, UnicodeDecodeError):
        return None
    diff = "".join(
        difflib.unified_diff(live_lines, staged_lines, fromfile=f"yours/{rel}", tofile=f"update/{rel}")
    )
    # Hardening iteration 10: a huge live file (teacher accident) produced a
    # 41MB diff string — shipped as JSON into the browser DOM, the Settings
    # panel hangs. Cap what the surface returns; the files themselves are
    # untouched either way.
    _max_diff = 200_000
    if len(diff) > _max_diff:
        diff = diff[:_max_diff] + "\n… diff truncated (files differ beyond this point) …\n"
    return diff


def resolve_pending(rel: str, action: str) -> dict:
    """Resolve one parked update. ``keep_mine`` keeps the teacher's copy
    and stops asking for this ship; ``take_new`` archives the teacher's
    copy FIRST (nothing is ever destroyed), then installs the staged
    version atomically."""
    if action not in ("keep_mine", "take_new"):
        return {"status": "error", "error": "action must be keep_mine or take_new"}
    if not _is_safe_rel(rel):
        return {"status": "error", "error": "invalid update path"}
    manifest = load_manifest()
    if not manifest or rel not in _pending_map(manifest):
        return {"status": "error", "error": "no pending update for this path"}
    entry = manifest["pending"][rel]
    staged = pending_root() / rel
    live_path = live_root() / rel

    if action == "take_new":
        if not staged.is_file():
            return {"status": "error", "error": "staged update file is missing"}
        if live_path.is_symlink():
            # Hardening iteration 5: reconcile promises symlinks are never
            # touched — take_new must not silently replace the teacher's
            # link with a regular file. keep_mine remains available.
            return {
                "status": "error",
                "error": (
                    "your copy is a symbolic link — Lingua Viva won't replace it. "
                    "Choose 'Keep mine', or update the linked file yourself."
                ),
            }
        archived_to = None
        try:
            if live_path.is_file():
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                archive_path = archive_root() / f"{rel}.{stamp}"
                counter = 1
                while archive_path.exists():
                    archive_path = archive_root() / f"{rel}.{stamp}.{counter}"
                    counter += 1
                _atomic_write_bytes(archive_path, live_path.read_bytes())
                archived_to = str(archive_path)
            _atomic_write_bytes(live_path, staged.read_bytes())
        except OSError as exc:
            # Hardening iteration 6: an unreadable staged/live file raised
            # straight through to a route 500. Archive-before-replace and
            # manifest-write-last mean nothing was lost — the pending entry
            # stays, so the teacher can simply retry.
            return {"status": "error", "error": f"could not apply the update: {exc}"}
    else:
        archived_to = None

    manifest.setdefault("artifacts", {})[rel] = {
        "hash": entry.get("new_hash"),
        "shipped_in": entry.get("shipped_in"),
        "schema_version": _artifact_schema_version(staged if staged.is_file() else live_path),
    }
    del manifest["pending"][rel]
    try:
        staged.unlink(missing_ok=True)
    except OSError:
        pass
    _write_manifest(manifest)  # LAST operation
    return {"status": "resolved", "action": action, "path": rel, "archived_to": archived_to}


# --------------------------------------------------------------------------
# Namespacing (Phase 4)
# --------------------------------------------------------------------------

def validate_user_artifact_id(artifact_id: str) -> tuple[bool, str]:
    """Creation-time gate: user-created artifact IDs must not use the
    reserved shipped namespace. Returns (ok, message)."""
    lowered = str(artifact_id or "").strip().casefold()
    for prefix in RESERVED_ID_PREFIXES:
        if lowered.startswith(prefix.casefold()):
            return False, (
                f"'{artifact_id}' starts with the reserved '{prefix}' prefix — "
                "that namespace belongs to shipped Lingua Viva artifacts. "
                "Pick a name that doesn't start with it."
            )
    return True, "ok"
