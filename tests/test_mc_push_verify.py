"""Tests for mc_push's live-verification helpers.

Updated 2026-08-17: synced mc_push.py from Mission Canvas. The old
_bump_site_pins / _check_site_pins helpers are gone — auto-release.yml
handles site pinning in CI now. Tests updated to cover the current
_verify_live and _stale_vs_main functions.
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mc_push.py"


def _load_mc_push():
    spec = importlib.util.spec_from_file_location("mc_push", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mc_push"] = module
    spec.loader.exec_module(module)
    return module


mc_push = _load_mc_push()


SITE_HTML = """
<a href="https://github.com/lingua-viva/learning-architecture/releases/download/desktop-v0.2.60/LinguaViva-Setup.exe">Windows</a>
<a href="https://github.com/lingua-viva/learning-architecture/releases/download/desktop-v0.2.60/LinguaViva.dmg">macOS</a>
"""


class TestVerifyLive:
    """Exercise _verify_live's decision logic with a stubbed network."""

    def _ctx(self):
        ctx = mc_push.Context()
        ctx.site_url = "https://linguaviva.art"
        ctx.gh_repo = "lingua-viva/learning-architecture"
        return ctx

    def test_matching_tag_passes(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, SITE_HTML))
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.60",
                                    attempts=1, delay=0) is True

    def test_stale_pin_fails_with_expected_tag(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, SITE_HTML))
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.99",
                                    attempts=1, delay=0) is False

    def test_no_pin_fails_with_expected_tag(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, "<p></p>"))
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.60",
                                    attempts=1, delay=0) is False

    def test_no_expected_tag_reports_whatever_is_live(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, SITE_HTML))
        assert mc_push._verify_live(self._ctx(), None, attempts=1, delay=0) is True

    def test_no_tag_on_site_fails_without_expected(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, "<p></p>"))
        assert mc_push._verify_live(self._ctx(), None, attempts=1, delay=0) is False

    def test_unreachable_site_fails(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (1, ""))
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.60",
                                    attempts=1, delay=0) is False


class TestContextDetect:
    """Verify context detection classifies repos correctly."""

    def test_lv_context_detects_auto_release(self, tmp_path):
        # Simulate LV repo structure
        (tmp_path / "desktop").mkdir()
        (tmp_path / "desktop" / "package.json").write_text(
            json.dumps({"name": "lingua-viva", "version": "0.2.60"})
        )
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        (tmp_path / ".github" / "workflows" / "auto-release.yml").write_text("on: push")
        (tmp_path / ".git").mkdir()

        ctx = mc_push.Context()
        ctx.repo_root = tmp_path
        ctx._detect_lv()
        assert ctx.kind == "lingua-viva"
        assert ctx.has_auto_release is True
        assert ctx.site_url == "https://linguaviva.art"
        assert ctx.gh_repo == "lingua-viva/learning-architecture"


class TestFreshnessRecording:
    """Verify three-state freshness verdicts."""

    def test_fresh_is_not_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mc_push, "FRESHNESS_FILE", tmp_path / "f.json")
        is_stale, msg = mc_push._record_freshness("fresh", "all good")
        assert is_stale is False
        assert "all good" in msg

    def test_stale_is_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mc_push, "FRESHNESS_FILE", tmp_path / "f.json")
        is_stale, msg = mc_push._record_freshness("stale", "behind")
        assert is_stale is True

    def test_unknown_is_not_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mc_push, "FRESHNESS_FILE", tmp_path / "f.json")
        is_stale, msg = mc_push._record_freshness("unknown", "unreachable")
        assert is_stale is False

    def test_invalid_state_degrades_to_unknown(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mc_push, "FRESHNESS_FILE", tmp_path / "f.json")
        is_stale, msg = mc_push._record_freshness("bogus", "typo")
        assert is_stale is False
        assert "unrecognised" in msg
        data = json.loads((tmp_path / "f.json").read_text())
        assert data["state"] == "unknown"
