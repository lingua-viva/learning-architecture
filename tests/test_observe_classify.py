from fastapi.testclient import TestClient

from src.lingua_viva.reasoning import ReasonResult, ReasoningEngine
from src.web import app


client = TestClient(app)


def test_observe_classify_returns_validated_proposal(monkeypatch):
    async def fake_reason(self, query, **kwargs):
        assert query == "The learner now speaks at B1 and has improved this month."
        assert "template_type" in kwargs["system_prompt"]
        assert kwargs["model"].startswith("ollama/")
        return ReasonResult(
            content=(
                '{"template_type":"cefr","cefr_dimension":"speaking",'
                '"cefr_level_observed":"B1","cefr_direction":"progressing",'
                '"sel_domain":null,"sel_valence":null,"urgency_flag":false}'
            ),
            confidence=0.9,
            model_used="ollama/test",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", fake_reason)
    response = client.post(
        "/api/observe/classify",
        json={
            "student_id": "student-example",
            "raw_transcript": "The learner now speaks at B1 and has improved this month.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["template_type"] == "cefr"
    assert body["proposal"]["cefr_dimension"] == "speaking"
    assert body["proposal"]["cefr_level_observed"] == "B1"
    assert body["proposal"]["cefr_direction"] == "progressing"
    assert body["proposal"]["urgency_flag"] is False
    assert body["writes_made"] == 0
    assert body["teacher_confirmation_required"] is True
    assert body["suggestions_available"] is True
    assert body["proposal"]["classification_guidance"]["scaffolding_level"] == "intermediate"


def test_observe_classify_rejects_empty_transcript():
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "  "},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "raw_transcript is required"


def test_observe_classify_degrades_to_nulls_without_model(monkeypatch):
    async def no_model(self, query, **kwargs):
        return ReasonResult(
            content="[Local reasoning - no model available]",
            confidence=0.0,
            model_used="none",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", no_model)
    response = client.post(
        "/api/observe/classify",
        json={
            "student_id": "student-example",
            "raw_transcript": "The learner participated in the group.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model_used"] == "none"
    assert body["suggestions_available"] is False
    assert body["writes_made"] == 0
    assert all(
        body["proposal"][key] is None
        for key in (
            "template_type",
            "cefr_dimension",
            "cefr_level_observed",
            "cefr_direction",
            "sel_domain",
            "sel_valence",
            "urgency_flag",
            "support_category",
            "need_statement",
            "strength_statement",
            "strategy_statement",
            "strategy_outcome",
            "evidence_summary",
        )
    )
    assert body["proposal"]["support_entries"] == []


def test_observe_classify_discards_malformed_or_invalid_fields(monkeypatch):
    async def malformed(self, query, **kwargs):
        return ReasonResult(
            content='Result: {"template_type":"medical","urgency_flag":"yes"}',
            confidence=0.2,
            model_used="ollama/test",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", malformed)
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "A short note."},
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["support_entries"] == []
    assert proposal["template_type"] is None
    assert proposal["urgency_flag"] is None


def test_observe_classify_rejects_oversized_transcript():
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "x" * 4001},
    )
    assert response.status_code == 413


def test_observe_classify_treats_local_breaker_message_as_degraded(monkeypatch):
    async def breaker_message(self, query, **kwargs):
        return ReasonResult(
            content="Ollama appears to be down - check if it's running, then try again.",
            confidence=0.0,
            model_used="ollama/qwen2.5:3b",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", breaker_message)
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "A short note."},
    )
    assert response.status_code == 200
    assert response.json()["model_used"] == "none"
    assert response.json()["suggestions_available"] is False


def test_observe_classify_normalizes_sel_domain_and_ignores_later_objects(monkeypatch):
    async def extra_object(self, query, **kwargs):
        return ReasonResult(
            content=(
                '```json\n{"template_type":"sel_positive","sel_domain":"  peer\\n'
                ' collaboration  ","sel_valence":"positive","urgency_flag":false}\n```'
                '\nExample only: {"urgency_flag":true}'
            ),
            confidence=0.8,
            model_used="ollama/test",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", extra_object)
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "A short note."},
    )
    proposal = response.json()["proposal"]
    assert proposal["sel_domain"] == "peer collaboration"
    assert proposal["urgency_flag"] is False


def test_observe_classify_exception_degrades_without_blocking(monkeypatch):
    async def unavailable(self, query, **kwargs):
        raise TimeoutError("local model unavailable")

    monkeypatch.setattr(ReasoningEngine, "reason", unavailable)
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "A short note."},
    )
    assert response.status_code == 200
    assert response.json()["model_used"] == "none"
    assert response.json()["proposal"]["support_entries"] == []


def test_observe_classify_parses_support_category_and_statements(monkeypatch):
    async def fake_reason(self, query, **kwargs):
        return ReasonResult(
            content=(
                '{"template_type":"literacy",'
                '"support_category":"executive_functioning",'
                '"need_statement":"Needs checklist for multi-step instructions",'
                '"strength_statement":"Strong visual memory",'
                '"strategy_statement":"Step-by-step visual card strip",'
                '"strategy_outcome":"worked",'
                '"evidence_summary":"Observed during independent math station"}'
            ),
            confidence=0.9,
            model_used="ollama/test",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", fake_reason)
    response = client.post(
        "/api/observe/classify",
        json={
            "student_id": "student-example",
            "raw_transcript": "Student responded well to the visual card strip.",
        },
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["support_category"] == "executive_functioning"
    assert proposal["need_statement"] == "Needs checklist for multi-step instructions"
    assert proposal["strength_statement"] == "Strong visual memory"
    assert proposal["strategy_statement"] == "Step-by-step visual card strip"
    assert proposal["strategy_outcome"] == "worked"
    assert proposal["evidence_summary"] == "Observed during independent math station"
    assert proposal["support_entries"][0]["support_category"] == "executive_functioning"
    assert proposal["support_entries"][0]["teacher_confirmed"] is False
    assert proposal["classification_guidance"]["category_definitions"][0]["category_id"] == "executive_functioning"


def test_observe_classify_discards_invalid_support_category_and_strategy_outcome(monkeypatch):
    async def invalid_proposal(self, query, **kwargs):
        return ReasonResult(
            content='{"support_category":"fake_category","strategy_outcome":"maybe"}',
            confidence=0.5,
            model_used="ollama/test",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", invalid_proposal)
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "Test transcript"},
    )
    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["support_category"] is None
    assert proposal["strategy_outcome"] is None
    assert proposal["support_entries"] == []


def test_observe_classify_accepts_multi_category_support_entries(monkeypatch):
    async def fake_reason(self, query, **kwargs):
        return ReasonResult(
            content=(
                '{"support_entries":['
                '{"support_category":"executive_functioning","need_statement":"Needs task sequence checklist","context_tags":{"language":"en","setting":"small_group"}},'
                '{"support_category":"communication_and_language","strength_statement":"Explains ideas clearly in Italian","context_tags":{"language":"it","setting":"classroom"}}'
                ']}'
            ),
            confidence=0.9,
            model_used="ollama/test",
        )

    monkeypatch.setattr(ReasoningEngine, "reason", fake_reason)
    response = client.post(
        "/api/observe/classify",
        json={"student_id": "student-example", "raw_transcript": "A mixed observation."},
    )
    proposal = response.json()["proposal"]
    assert [entry["support_category"] for entry in proposal["support_entries"]] == [
        "executive_functioning",
        "communication_and_language",
    ]
    assert proposal["support_entries"][0]["context_tags"] == {
        "language": "en",
        "setting": "small_group",
    }
    assert response.json()["writes_made"] == 0
