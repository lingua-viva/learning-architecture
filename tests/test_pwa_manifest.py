from src.pwa import build_manifest


def test_manifest_defaults_from_static_file():
    manifest = build_manifest(env={})
    assert manifest["name"] == "Lingua Viva"
    assert manifest["display"] == "standalone"
    assert any(icon["src"] == "/icons/icon-maskable.png" for icon in manifest["icons"])
    shortcut_names = {shortcut["name"] for shortcut in manifest["shortcuts"]}
    assert shortcut_names == {"Capture Observation", "Plan Lesson"}
    assert "Research" not in shortcut_names
    assert "Protect" not in shortcut_names


def test_manifest_environment_overrides_client_branding():
    manifest = build_manifest(env={
        "LV_PWA_NAME": "Lingua Viva - Teacher",
        "LV_PWA_SHORT_NAME": "LV Teach",
        "LV_PWA_THEME_COLOR": "#1f6f4a",
        "LV_PWA_DEFAULT_INTENT": "protect",
    })
    assert manifest["name"] == "Lingua Viva - Teacher"
    assert manifest["short_name"] == "LV Teach"
    assert manifest["theme_color"] == "#1f6f4a"
    assert manifest["start_url"] == "/?intent=PROTECT"
