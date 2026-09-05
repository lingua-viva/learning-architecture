from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_home_is_first_teacher_sidebar_item_and_default():
    html = (ROOT / "static" / "index.html").read_text()

    assert 'view: "home"' in html
    assert '["home", "Home", "🏠"]' in html
    assert html.index('["home", "Home", "🏠"]') < html.index('["plan", "Plan", "📋"]')


def test_home_renders_brief_and_action_links():
    html = (ROOT / "static" / "index.html").read_text()

    assert "Good morning." in html
    assert "Set up your schedule in Settings" in html
    assert "/api/brief" in html
    assert "Go to Observe" in html
    assert "Go to Students" in html
    assert "Ready for class" in html
    assert 'state.view = "observe"' in html
    assert 'state.view = "students"' in html


def test_home_does_not_surface_doctor_health_warning_copy():
    html = (ROOT / "static" / "index.html").read_text()
    home = html[html.index("async function renderHome()") : html.index("async function renderObserve()")]

    assert "System:" not in home
    assert "<h3>Health</h3>" not in home
    assert "data.health?.summary" not in home


def test_logo_click_returns_to_students():
    html = (ROOT / "static" / "index.html").read_text()

    assert 'id="brand-home"' in html
    # Operator 2026-09-05: both schools open on Students; Home is retired.
    assert 'state.view = defaultViewFor(state.role)' in html
    assert 'if (role === "coordinator") return "programme";' in html
    assert 'return "students";' in html


def test_still_i_rise_photo_is_mounted_in_topbar():
    html = (ROOT / "static" / "index.html").read_text()

    assert 'class="topbar-actions"' in html
    assert 'src="/assets/still-i-rise-topbar.jpg"' in html
    assert 'class="sir-topbar-photo"' in html


def test_version_badge_wired_in_topbar():
    """F4: the UI must surface the app version somewhere always-reachable."""
    html = (ROOT / "static" / "index.html").read_text()

    assert 'id="app-version"' in html
    assert "lvDesktop.getVersion" in html
    assert '"/api/health"' in html


def test_first_launch_welcome_explains_privacy_and_lands_on_students():
    html = (ROOT / "static" / "index.html").read_text()

    assert "World-class tools for world-class schools." in html
    assert "Everything stays on your machine. No student data leaves. Ever." in html
    assert "I am a:" in html
    # Both teacher profiles now land on Students; coordinator opens Programme.
    assert 'state.view = defaultViewFor(role)' in html
    assert 'return "students";' in html
