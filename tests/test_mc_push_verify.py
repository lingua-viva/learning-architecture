"""Tests for mc_push's live-verification + site-pin bump helpers.

Why this exists (2026-07-26): the 07-25 ship found `_verify_live()` grepped
for ANY desktop-v string and returned True on every branch — "Shipped ✓" was
reported while docs/index.html sat two releases stale (0.2.7 vs 0.2.9).
The same session in Mission Canvas caught an INDEX row claiming "built"
before the code existed. Same lesson both times: a status claim must be
compared against the exact expected state, not pattern-matched for presence.

These tests pin the pure helpers so the trap can't silently reopen.
"""

import importlib.util
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
<a href="https://github.com/lingua-viva/learning-architecture/releases/download/desktop-v0.2.7/LinguaViva-Setup.exe">Windows</a>
<a href="https://github.com/lingua-viva/learning-architecture/releases/download/desktop-v0.2.7/LinguaViva.dmg">macOS</a>
"""


class TestBumpSitePins:
    def test_rewrites_every_pin(self):
        new_html, count = mc_push._bump_site_pins(SITE_HTML, "desktop-v0.2.9")
        assert count == 2
        assert "desktop-v0.2.7" not in new_html
        assert new_html.count("desktop-v0.2.9") == 2

    def test_idempotent_on_current_tag(self):
        once, _ = mc_push._bump_site_pins(SITE_HTML, "desktop-v0.2.9")
        twice, count = mc_push._bump_site_pins(once, "desktop-v0.2.9")
        assert twice == once
        assert count == 2  # re-matched, but content unchanged

    def test_mixed_stale_pins_all_converge(self):
        html = SITE_HTML + '<a href=".../desktop-v0.1.0/x">old</a>'
        new_html, count = mc_push._bump_site_pins(html, "desktop-v0.3.0")
        assert count == 3
        assert set(__import__("re").findall(r"desktop-v[\d.]+", new_html)) == {
            "desktop-v0.3.0"
        }

    def test_no_pins_is_a_noop(self):
        new_html, count = mc_push._bump_site_pins("<p>no links</p>", "desktop-v1.0.0")
        assert count == 0
        assert new_html == "<p>no links</p>"


class TestCheckSitePins:
    def test_stale_pin_detected(self):
        served, stale = mc_push._check_site_pins(SITE_HTML, "desktop-v0.2.9")
        assert served == ["desktop-v0.2.7"]
        assert stale == ["desktop-v0.2.7"]

    def test_current_pin_passes(self):
        html, _ = mc_push._bump_site_pins(SITE_HTML, "desktop-v0.2.9")
        served, stale = mc_push._check_site_pins(html, "desktop-v0.2.9")
        assert served == ["desktop-v0.2.9"]
        assert stale == []

    def test_mixed_pins_flag_only_stale(self):
        html = SITE_HTML.replace(
            "desktop-v0.2.7/LinguaViva.dmg", "desktop-v0.2.9/LinguaViva.dmg"
        )
        served, stale = mc_push._check_site_pins(html, "desktop-v0.2.9")
        assert served == ["desktop-v0.2.7", "desktop-v0.2.9"]
        assert stale == ["desktop-v0.2.7"]

    def test_no_pins_at_all(self):
        served, stale = mc_push._check_site_pins("<p>empty</p>", "desktop-v0.2.9")
        assert served == []
        assert stale == []


class TestVerifyLive:
    """Exercise _verify_live's decision logic with a stubbed network."""

    def _ctx(self):
        ctx = mc_push.Context()
        ctx.site_url = "https://linguaviva.art"
        return ctx

    def test_stale_pin_fails_with_expected_tag(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, SITE_HTML))
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.9") is False

    def test_no_pin_fails_with_expected_tag(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, "<p></p>"))
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.9") is False

    def test_correct_pin_and_live_assets_pass(self, monkeypatch):
        html, _ = mc_push._bump_site_pins(SITE_HTML, "desktop-v0.2.9")

        def fake_run_quiet(cmd, cwd=None):
            if cmd.startswith("curl -sI"):
                return 0, "200"
            return 0, html

        monkeypatch.setattr(mc_push, "run_quiet", fake_run_quiet)
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.9") is True

    def test_dead_download_url_fails(self, monkeypatch):
        html, _ = mc_push._bump_site_pins(SITE_HTML, "desktop-v0.2.9")

        def fake_run_quiet(cmd, cwd=None):
            if cmd.startswith("curl -sI"):
                return 0, "404"
            return 0, html

        monkeypatch.setattr(mc_push, "run_quiet", fake_run_quiet)
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.9") is False

    def test_unreachable_site_stays_nonfatal(self, monkeypatch):
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (1, ""))
        assert mc_push._verify_live(self._ctx(), "desktop-v0.2.9") is True

    def test_no_expected_tag_never_fails(self, monkeypatch):
        # MC auto-release path: informational only, legacy behavior preserved.
        monkeypatch.setattr(mc_push, "run_quiet", lambda cmd, cwd=None: (0, SITE_HTML))
        assert mc_push._verify_live(self._ctx(), None) is True
