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
    assert 'state.view = "observe"' in html
    assert 'state.view = "students"' in html


def test_logo_click_returns_to_home():
    html = (ROOT / "static" / "index.html").read_text()

    assert 'id="brand-home"' in html
    assert 'state.view = state.role === "coordinator" ? "programme" : "home"' in html


def test_first_launch_welcome_explains_privacy_and_lands_on_home():
    html = (ROOT / "static" / "index.html").read_text()

    assert "A teacher workbench for Italian language instruction." in html
    assert "Everything stays on your machine. No student data leaves. Ever." in html
    assert "I am a:" in html
    assert 'state.view = role === "coordinator" ? "programme" : "home"' in html
