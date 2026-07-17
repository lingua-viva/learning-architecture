from fastapi.testclient import TestClient

from src.web import app


client = TestClient(app)


def test_pwa_root_serves_static_shell():
    response = client.get("/")
    assert response.status_code == 200
    assert 'rel="manifest"' in response.text
    assert 'navigator.serviceWorker.register("/sw.js")' in response.text


def test_pwa_asset_routes():
    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert 'url.pathname === "/api/query"' in sw.text

    icon = client.get("/icons/icon-192.png")
    assert icon.status_code == 200
    assert icon.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_default_branding_is_lingua_viva():
    """The shipped default must read "Lingua Viva" wherever a teacher looks."""
    manifest = client.get("/manifest.json")
    assert manifest.json()["name"] == "Lingua Viva"
    assert manifest.json()["short_name"] == "Lingua Viva"

    root = client.get("/")
    assert "Lingua Viva" in root.text


def test_manifest_route_uses_environment_overrides(monkeypatch):
    monkeypatch.setenv("LV_PWA_NAME", "Lingua Viva - Teacher")
    monkeypatch.setenv("LV_PWA_THEME_COLOR", "#005f73")
    response = client.get("/manifest.json")
    assert response.status_code == 200
    assert response.json()["name"] == "Lingua Viva - Teacher"
    assert response.json()["theme_color"] == "#005f73"


def test_share_target_redirects_to_prefilled_query():
    response = client.post(
        "/",
        data={"title": "Shared", "text": "Hello", "url": "https://example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?shared=Shared+Hello+https%3A%2F%2Fexample.com"
