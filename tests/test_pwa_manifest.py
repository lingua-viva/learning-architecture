from src.pwa import build_manifest


def test_manifest_defaults_from_static_file():
    manifest = build_manifest(env={})
    assert manifest["name"] == "Still I Rise"
    assert manifest["display"] == "standalone"
    assert any(icon["src"] == "/icons/icon-maskable.png" for icon in manifest["icons"])


def test_manifest_environment_overrides_client_branding():
    manifest = build_manifest(env={
        "MC_PWA_NAME": "MC - Teacher",
        "MC_PWA_SHORT_NAME": "MC Teach",
        "MC_PWA_THEME_COLOR": "#1f6f4a",
        "MC_PWA_DEFAULT_INTENT": "protect",
    })
    assert manifest["name"] == "MC - Teacher"
    assert manifest["short_name"] == "MC Teach"
    assert manifest["theme_color"] == "#1f6f4a"
    assert manifest["start_url"] == "/?intent=PROTECT"
