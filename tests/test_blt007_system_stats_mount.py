from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _health_renderer() -> str:
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    start = html.index("async function renderHealth()")
    end = html.index("async function renderWhy()", start)
    return html[start:end]


def test_health_mounts_all_system_stats_fail_open():
    renderer = _health_renderer()

    assert 'try { stats = await api("/api/stats"); } catch {}' in renderer
    assert "stats && !stats.error" in renderer
    assert "<h3>System</h3>" in renderer
    for field in (
        "ontology_nodes",
        "domains",
        "knowledge_entries",
        "citations",
        "path_records",
        "gap_signals",
    ):
        assert f"${{stats.{field}}}" in renderer


def test_system_panel_follows_doctor_panel_and_reuses_stat_card_grid():
    renderer = _health_renderer()

    assert renderer.index("${statsPanel}") > renderer.index("bundle-result")
    assert '<div class="grid three" style="margin-top:10px;">' in renderer
    assert renderer.count('<div class="panel"><h3>${stats.') == 6
