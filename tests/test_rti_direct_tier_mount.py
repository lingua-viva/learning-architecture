from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _load_lens_renderer() -> str:
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    start = html.index("async function loadLens(")
    end = html.index("async function renderAssess()", start)
    return html[start:end]


def test_direct_tier_control_is_guarded_by_decision_controls():
    renderer = _load_lens_renderer()
    controls_start = renderer.index("const decisionControls = showDecisionControls")
    controls_end = renderer.index('` : "";', controls_start)
    controls = renderer[controls_start:controls_end]

    assert 'id="rti-tier-select"' in controls
    assert 'id="rti-set-tier"' in controls
    assert 'id="rti-tier-status"' in controls
    assert all(f'value="{tier}"' in controls for tier in (1, 2, 3))
    assert 'if (!showDecisionControls) return;' in renderer


def test_direct_tier_handler_puts_refreshes_and_reports_errors():
    renderer = _load_lens_renderer()

    assert "async function handleSetTier()" in renderer
    assert "/api/students/${state.selectedStudent}/rti" in renderer
    assert 'method: "PUT"' in renderer
    assert "JSON.stringify({new_tier: newTier})" in renderer
    assert "await loadLens(targetId, showDecisionControls);" in renderer
    assert '"Tier updated."' in renderer
    assert 'data.error || "Failed."' in renderer
    assert '"Network error."' in renderer
    assert '$("rti-set-tier").addEventListener("click", handleSetTier);' in renderer
