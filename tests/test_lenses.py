"""
Lens Engine Tests — activation rules, including the education-domain
extensions (list-valued on_domain, on_signal_keywords) added when wiring
lenses/education/ into the engine.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lenses.engine import Lens, LensEngine


def test_engine_loads_education_subdir():
    engine = LensEngine()
    assert "curriculum-designer" in engine.lenses


def test_on_intent_activation_unchanged():
    lens = Lens({"name": "x", "activation": {"on_intent": "PROTECT"}})
    assert lens.should_activate(intent="PROTECT") is True
    assert lens.should_activate(intent="CREATE") is False


def test_on_domain_single_string_still_works():
    lens = Lens({"name": "x", "activation": {"on_domain": "assessment"}})
    assert lens.should_activate(domain="assessment") is True
    assert lens.should_activate(domain="curriculum") is False


def test_on_domain_list_activates_on_any_member():
    lens = Lens({"name": "x", "activation": {"on_domain": ["curriculum", "teacher"]}})
    assert lens.should_activate(domain="curriculum") is True
    assert lens.should_activate(domain="teacher") is True
    assert lens.should_activate(domain="parent") is False


def test_on_confidence_below_unchanged():
    lens = Lens({"name": "x", "activation": {"on_confidence_below": 0.6}})
    assert lens.should_activate(confidence=0.4) is True
    assert lens.should_activate(confidence=0.9) is False


def test_on_signal_keywords_matches_query_text():
    lens = Lens({"name": "x", "activation": {"on_signal_keywords": ["refugee", "trauma"]}})
    assert lens.should_activate(query="This student is a refugee from Syria") is True
    assert lens.should_activate(query="What is 2+2") is False


def test_on_signal_keywords_no_query_does_not_activate():
    lens = Lens({"name": "x", "activation": {"on_signal_keywords": ["refugee"]}})
    assert lens.should_activate(query=None) is False


def test_user_requested_overrides_everything():
    lens = Lens({"name": "x", "activation": {"on_intent": "PROTECT"}})
    assert lens.should_activate(intent="CREATE", user_requested=True) is True


def test_get_active_lenses_passes_query_through():
    engine = LensEngine()
    engine.lenses = {
        "trauma-test": Lens({"name": "trauma-test", "activation": {"on_signal_keywords": ["refugee"]}}),
        "unrelated": Lens({"name": "unrelated", "activation": {"on_intent": "DECIDE"}}),
    }
    active = engine.get_active_lenses(query="working with a refugee student")
    names = [l.name for l in active]
    assert "trauma-test" in names
    assert "unrelated" not in names
