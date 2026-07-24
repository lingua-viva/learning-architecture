"""Route reachability gate regression tests
(dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md §5,
SPEC_LV_ROUTE_REACHABILITY_GATE_2026-07-23.md).
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_route_reachability.py"
MANIFEST = REPO / "contracts" / "ROUTE_REACHABILITY.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_route_reachability", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_reachability_check_passes_against_the_real_repo():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_live_route_is_classified_exactly_once():
    module = _load_module()
    live = module.live_routes()
    manifest = module.load_manifest()
    reachable = {e["route"] for e in manifest["reachable_from_ui"]}
    backend_only = {e["route"] for e in manifest["intentionally_backend_only"]}

    unclassified = [r for r in set(live) if r not in reachable and r not in backend_only]
    both = reachable & backend_only
    assert not unclassified, f"routes missing from the manifest entirely: {unclassified}"
    assert not both, f"routes listed in both lists: {both}"


def test_backend_only_entries_have_a_valid_status_and_reason():
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    for entry in data["intentionally_backend_only"]:
        assert entry.get("status") in ("permanent", "deferred_undecided"), entry
        assert entry.get("reason"), f"{entry['route']} has no reason"


def test_reachable_entries_have_a_call_site():
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    for entry in data["reachable_from_ui"]:
        assert entry.get("call_site"), f"{entry['route']} has no call_site"


def test_unclassified_new_route_fails_the_check(tmp_path, monkeypatch):
    module = _load_module()
    fake_web = tmp_path / "web.py"
    fake_web.write_text(
        '@app.get("/api/health")\nasync def health():\n    ...\n'
        '@app.get("/api/brand_new_unclassified_route")\nasync def new_route():\n    ...\n',
        encoding="utf-8",
    )
    fake_manifest = tmp_path / "manifest.yaml"
    fake_manifest.write_text(
        "reachable_from_ui:\n"
        "  - route: \"GET /api/health\"\n"
        "    call_site: \"__root_document__\"\n"
        "intentionally_backend_only: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "WEB_PY", fake_web)
    monkeypatch.setattr(module, "MANIFEST", fake_manifest)
    assert module.check() == 1


def test_removed_call_site_fails_the_check(tmp_path, monkeypatch):
    module = _load_module()
    fake_web = tmp_path / "web.py"
    fake_web.write_text('@app.get("/api/thing")\nasync def thing():\n    ...\n', encoding="utf-8")
    fake_index = tmp_path / "index.html"
    fake_index.write_text("<html>no api calls here</html>", encoding="utf-8")
    fake_manifest = tmp_path / "manifest.yaml"
    fake_manifest.write_text(
        "reachable_from_ui:\n"
        "  - route: \"GET /api/thing\"\n"
        "    call_site: 'api(\"/api/thing\")'\n"
        "    file: index.html\n"
        "intentionally_backend_only: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "WEB_PY", fake_web)
    monkeypatch.setattr(module, "MANIFEST", fake_manifest)
    monkeypatch.setattr(module, "REPO", tmp_path)
    assert module.check() == 1


def test_duplicate_route_registration_fails_the_check(tmp_path, monkeypatch):
    module = _load_module()
    fake_web = tmp_path / "web.py"
    fake_web.write_text(
        '@app.get("/api/thing")\nasync def thing():\n    ...\n'
        '@app.get("/api/thing")\nasync def thing_again():\n    ...\n',
        encoding="utf-8",
    )
    fake_manifest = tmp_path / "manifest.yaml"
    fake_manifest.write_text(
        "reachable_from_ui:\n"
        "  - route: \"GET /api/thing\"\n"
        "    call_site: \"__root_document__\"\n"
        "intentionally_backend_only: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "WEB_PY", fake_web)
    monkeypatch.setattr(module, "MANIFEST", fake_manifest)
    assert module.check() == 1


def test_stale_manifest_entry_fails_the_check_directly(tmp_path, monkeypatch):
    """Stale entries must fail `check()` itself, not just show up under
    --sync-stale — otherwise catching them depends on someone remembering to
    run the separate command, which is exactly the failure mode this gate
    exists to remove."""
    module = _load_module()
    fake_web = tmp_path / "web.py"
    fake_web.write_text('@app.get("/api/still-here")\nasync def still_here():\n    ...\n', encoding="utf-8")
    fake_manifest = tmp_path / "manifest.yaml"
    fake_manifest.write_text(
        "reachable_from_ui:\n"
        "  - route: \"GET /api/still-here\"\n"
        "    call_site: \"__root_document__\"\n"
        "intentionally_backend_only:\n"
        "  - route: \"GET /api/long-gone\"\n"
        "    status: permanent\n"
        "    reason: \"historical\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "WEB_PY", fake_web)
    monkeypatch.setattr(module, "MANIFEST", fake_manifest)
    assert module.check() == 1


def test_sync_stale_reports_manifest_entries_for_removed_routes(tmp_path, monkeypatch, capsys):
    module = _load_module()
    fake_web = tmp_path / "web.py"
    fake_web.write_text('@app.get("/api/still-here")\nasync def still_here():\n    ...\n', encoding="utf-8")
    fake_manifest = tmp_path / "manifest.yaml"
    fake_manifest.write_text(
        "reachable_from_ui:\n"
        "  - route: \"GET /api/still-here\"\n"
        "    call_site: \"__root_document__\"\n"
        "intentionally_backend_only:\n"
        "  - route: \"GET /api/long-gone\"\n"
        "    status: permanent\n"
        "    reason: \"historical\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "WEB_PY", fake_web)
    monkeypatch.setattr(module, "MANIFEST", fake_manifest)
    module.sync_stale()
    out = capsys.readouterr().out
    assert "GET /api/long-gone" in out
