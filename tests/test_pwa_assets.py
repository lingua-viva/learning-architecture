from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_pwa_assets_exist():
    for rel in [
        "static/index.html",
        "static/manifest.json",
        "static/sw.js",
        "static/offline.html",
        "static/icons/icon.svg",
        "static/icons/icon-192.png",
        "static/icons/icon-512.png",
        "static/icons/icon-maskable.png",
    ]:
        assert (ROOT / rel).exists(), rel


def test_index_registers_service_worker_and_manifest():
    html = (ROOT / "static" / "index.html").read_text()
    assert 'rel="manifest"' in html
    assert 'navigator.serviceWorker.register("/sw.js")' in html
    assert 'fetch("/api/query"' in html
    assert "/icons/icon-192.png" in html
    assert "queue-actions" in html


def test_service_worker_queues_governed_query_endpoint():
    sw = (ROOT / "static" / "sw.js").read_text()
    assert 'url.pathname === "/api/query"' in sw
    assert "lv-replay-queue" in sw
    assert 'fetch("/api/query"' in sw
    assert "/icons/icon-maskable.png" in sw
    assert "LV_REPLAY_NOW" in sw
    assert "LV_CLEAR_QUEUE" in sw
