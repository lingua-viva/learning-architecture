"""Evidence + Ethos Traits — SPEC_LV_EVIDENCE_ETHOS_TRAITS_2026-08-01.

Unified append-only evidence ledger: documents from Sources + direct
teacher feedback attached to students against support categories, ethos
traits, strengths, and background. Evidence summaries flow into parent
report drafts BEHIND the existing safety gates (`_strip_parent_output` +
`check_publication_safety`) — the gate-order regression test (group 5)
was written before the report wiring existed, and must keep failing
loudly if anyone ever routes evidence text around the gates.

Per operator ruling 2026-08-01 ("adapt to ethos layer"): the trait list
lives in ethos.yaml, ethos writes validate against `ethos.trait_ids()`,
and the shipped `add_ethos_evidence` path and the new ledger share one
core writer so evidence never forks.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.education.student_lens import StudentLensStore
from src.web import app


def _isolate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LV_STUDENT_DB_PATH", str(tmp_path / "students.db"))
    monkeypatch.setenv("LV_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LV_PRIVACY_LOG_PATH", str(tmp_path / "privacy.ndjson"))
    monkeypatch.setenv("LV_REVISION_LOG_PATH", str(tmp_path / "revision.ndjson"))
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path / "config-home"))
    # Nonexistent path -> load_ethos() falls back to the built-in seed
    # taxonomy (ambition/bravery/care + learner attributes), deterministic.
    monkeypatch.setenv("LV_ETHOS_PATH", str(tmp_path / "ethos.yaml"))
    monkeypatch.delenv("LV_AUTH_MODE", raising=False)


def _break_ethos(tmp_path: Path):
    """An unloadable taxonomy — the 'no traits available' degraded state."""
    (tmp_path / "ethos.yaml").write_text("traits: 42\n", encoding="utf-8")


def _create_student(client: TestClient, name: str = "Marco Bianchi") -> str:
    created = client.post("/api/students", json={"display_name": name, "grade_level": "G3"})
    assert created.status_code == 200
    return created.json()["student_id"]


def _post_evidence(client: TestClient, student_id: str, **overrides):
    payload = {
        "teacher_id": "teacher-a",
        "kind": "teacher_feedback",
        "target_type": "support_category",
        "target_id": "communication_and_language",
        "summary": "Responded well to sentence starters in small group.",
        "confidence_level": "teacher_confirmed",
    }
    payload.update(overrides)
    return client.post(f"/api/students/{student_id}/evidence", json=payload)


def _list_evidence(client: TestClient, student_id: str, query: str = ""):
    res = client.get(f"/api/students/{student_id}/evidence{query}")
    assert res.status_code == 200
    return res.json()


def _seed_source_record(title: str = "Reading assessment scan") -> str:
    from src.lingua_viva.sources.ledger import upsert
    from src.lingua_viva.sources.schema import SourceRecord

    record = SourceRecord(
        source_record_id="src-test-1",
        source_type="local",
        source_id="local-test",
        container="imports",
        record_id="doc-1",
        title=title,
        uri="file:///tmp/doc.txt",
        retrieval_scope="metadata",
        created_at="2026-08-01T00:00:00+00:00",
        observed_at="2026-08-01T00:00:00+00:00",
        provenance="import",
    )
    upsert(record)
    return record.source_record_id


def _privacy_events(tmp_path: Path) -> list[dict]:
    path = tmp_path / "privacy.ndjson"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. Append / list / soft-delete; enum + target validation; bogus ref -> 400
# ---------------------------------------------------------------------------


def test_append_and_list_teacher_feedback(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = _post_evidence(client, sid)
        assert res.status_code == 200
        evidence_id = res.json()["evidence_id"]

        data = _list_evidence(client, sid)
        assert data["total"] == 1
        item = data["evidence"][0]
        assert item["evidence_id"] == evidence_id
        assert item["kind"] == "teacher_feedback"
        assert item["target_type"] == "support_category"
        assert item["deleted"] is False
        grouped = data["by_target"]["support_category"]["communication_and_language"]
        assert grouped[0]["evidence_id"] == evidence_id


def test_unknown_student_is_404(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert _post_evidence(client, "student-nope").status_code == 404
        assert client.get("/api/students/student-nope/evidence").status_code == 404
        assert client.delete("/api/students/student-nope/evidence/x").status_code == 404


def test_enum_and_target_validation(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        assert _post_evidence(client, sid, kind="rumor").status_code == 400
        assert _post_evidence(client, sid, target_type="vibes").status_code == 400
        assert _post_evidence(client, sid, target_id="not_a_category").status_code == 400
        assert _post_evidence(client, sid, summary="").status_code == 400
        assert _post_evidence(client, sid, summary="x" * 2001).status_code == 400
        assert _post_evidence(client, sid, confidence_level="gut_feeling").status_code == 400
        # background takes no target_id
        assert _post_evidence(
            client, sid, target_type="background", target_id="something"
        ).status_code == 400
        assert _post_evidence(
            client, sid, target_type="background", target_id=None
        ).status_code == 200


def test_document_requires_a_real_source_record(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        # No pointer at all -> 400.
        assert _post_evidence(client, sid, kind="document").status_code == 400
        # Bogus pointer -> 400.
        res = _post_evidence(
            client, sid, kind="document",
            source_ref={"source_record_id": "src-does-not-exist"},
        )
        assert res.status_code == 400
        # Real ledger record -> 200, ref enriched from ledger ground truth.
        record_id = _seed_source_record(title="Reading assessment scan")
        res = _post_evidence(
            client, sid, kind="document",
            source_ref={"source_record_id": record_id, "title": "client lie"},
        )
        assert res.status_code == 200
        item = _list_evidence(client, sid)["evidence"][0]
        assert item["source_ref"]["source_record_id"] == record_id
        assert item["source_ref"]["title"] == "Reading assessment scan"


def test_soft_delete_is_a_tombstone_not_a_hard_delete(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        evidence_id = _post_evidence(client, sid).json()["evidence_id"]

        res = client.delete(f"/api/students/{sid}/evidence/{evidence_id}")
        assert res.status_code == 200

        assert _list_evidence(client, sid)["total"] == 0
        tombstones = _list_evidence(client, sid, "?include_deleted=true")["evidence"]
        assert len(tombstones) == 1
        assert tombstones[0]["deleted"] is True
        assert tombstones[0]["deleted_at"]

        # Idempotent second delete; bogus id -> 404.
        assert client.delete(f"/api/students/{sid}/evidence/{evidence_id}").status_code == 200
        assert client.delete(f"/api/students/{sid}/evidence/nope").status_code == 404


def test_delete_is_scoped_to_the_student_in_the_url(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid_a = _create_student(client, "Marco Bianchi")
        sid_b = _create_student(client, "Sara Rossi")
        evidence_id = _post_evidence(client, sid_a).json()["evidence_id"]
        # Someone else's URL cannot tombstone this row.
        assert client.delete(f"/api/students/{sid_b}/evidence/{evidence_id}").status_code == 404
        assert _list_evidence(client, sid_a)["total"] == 1


# ---------------------------------------------------------------------------
# 2. Ethos rollup recompute correctness (ledger is ground truth)
# ---------------------------------------------------------------------------


def test_ethos_evidence_updates_rollups_and_mirrors_profile(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        first = _post_evidence(
            client, sid, target_type="ethos_trait", target_id="bravery",
            summary="Tried again after failing in front of the class.",
        )
        second = _post_evidence(
            client, sid, target_type="ethos_trait", target_id="bravery",
            summary="Volunteered to read aloud first.",
        )
        assert first.status_code == 200 and second.status_code == 200

        lens = client.get(f"/api/students/{sid}/lens").json()
        trait = lens["ethos_profile"]["traits"]["bravery"]
        assert trait["evidence_count"] == 2
        assert trait["last_evidence_at"]

        # Same uuid in both stores: the profile array mirrors the ledger.
        ledger = _list_evidence(client, sid, "?target_type=ethos_trait")["evidence"]
        assert {i["id"] for i in trait["evidence"]} == {r["evidence_id"] for r in ledger}

        # Soft-delete one -> rollup recomputed FROM the ledger, mirrored
        # profile item retired together.
        gone = first.json()["evidence_id"]
        assert client.delete(f"/api/students/{sid}/evidence/{gone}").status_code == 200
        lens = client.get(f"/api/students/{sid}/lens").json()
        trait = lens["ethos_profile"]["traits"]["bravery"]
        assert trait["evidence_count"] == 1
        retired = [i for i in trait["evidence"] if i["id"] == gone]
        assert retired and retired[0]["active"] is False


def test_ethos_writes_validate_against_taxonomy(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = _post_evidence(
            client, sid, target_type="ethos_trait", target_id="not_a_trait",
            summary="Should be rejected.",
        )
        assert res.status_code == 400
        assert "not_a_trait" in res.json()["error"]


def test_ethos_double_submit_is_idempotent(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        payload = dict(
            target_type="ethos_trait", target_id="care",
            summary="Helped a new classmate find the library.",
        )
        first = _post_evidence(client, sid, **payload).json()["evidence_id"]
        second = _post_evidence(client, sid, **payload).json()["evidence_id"]
        assert first == second
        assert _list_evidence(client, sid)["total"] == 1
        lens = client.get(f"/api/students/{sid}/lens").json()
        assert lens["ethos_profile"]["traits"]["care"]["evidence_count"] == 1


def test_shipped_add_ethos_evidence_path_writes_the_ledger_too(monkeypatch, tmp_path):
    """The bridge: the pre-existing ethos writer (used by
    confirm_ethos_suggestion) and the new ledger share one core writer —
    same uuid in the profile array and the evidence_records row."""
    _isolate(monkeypatch, tmp_path)
    with StudentLensStore(db_path=tmp_path / "s.db") as store:
        sid = store.create_lens(display_name="Test Student")
        profile = store.add_ethos_evidence(
            sid, "bravery", "Volunteered first.", "teacher-a",
            allowed_trait_ids=["bravery"],
        )
        item_id = profile["traits"]["bravery"]["evidence"][0]["id"]
        rows = store.list_evidence(sid, target_type="ethos_trait")
        assert [r["evidence_id"] for r in rows] == [item_id]
        assert rows[0]["kind"] == "teacher_feedback"
        assert profile["traits"]["bravery"]["evidence_count"] == 1


# ---------------------------------------------------------------------------
# 3. Broken/empty taxonomy -> no suggestions, surfaces hidden (never errors)
# ---------------------------------------------------------------------------


def test_taxonomy_endpoint_degrades_to_unavailable(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _break_ethos(tmp_path)
    with TestClient(app) as client:
        res = client.get("/api/ethos/taxonomy")
        assert res.status_code == 200
        assert res.json() == {"available": False, "ethos_name": None, "traits": []}


def test_taxonomy_endpoint_serves_the_seed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        data = client.get("/api/ethos/taxonomy").json()
        assert data["available"] is True
        ids = [t["id"] for t in data["traits"]]
        assert "bravery" in ids and "care" in ids


def test_classify_ethos_suggestions_degrade_to_empty(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _break_ethos(tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.post(
            "/api/observe/classify",
            json={"student_id": sid, "raw_transcript": "Marco showed courage today."},
        )
        assert res.status_code == 200
        assert res.json()["ethos_suggestions"] == []


def test_classify_suggests_traits_on_keyword_match(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        res = client.post(
            "/api/observe/classify",
            json={
                "student_id": sid,
                "raw_transcript": "Marco showed real courage reading aloud.",
            },
        )
        assert res.status_code == 200
        suggestions = res.json()["ethos_suggestions"]
        assert {"trait_id": "bravery", "matched_term": "courage", "label": "Bravery"} in suggestions
        # Word-boundary rule: 'scared' must not match 'care'.
        res = client.post(
            "/api/observe/classify",
            json={"student_id": sid, "raw_transcript": "Marco seemed scared of the test."},
        )
        assert all(s["trait_id"] != "care" for s in res.json()["ethos_suggestions"])


# ---------------------------------------------------------------------------
# 4. voice/act: ethos_suggestions additive; existing shape frozen
# ---------------------------------------------------------------------------

def _voice_observation(client: TestClient, sid: str, transcript: str):
    # Roster membership requires one prior observation by this teacher.
    captured = client.post(
        "/api/observe/capture",
        json={
            "student_id": sid,
            "teacher_id": "teacher-a",
            "transcript": "Private raw transcript phrase.",
            "template_type": "cefr",
            "cefr_dimension": "speaking",
            "cefr_level_observed": "A2",
            "cefr_direction": "progressing",
        },
    )
    assert captured.status_code == 200
    res = client.post(
        "/api/voice/act",
        json={"teacher_id": "teacher-a", "transcript": transcript},
    )
    assert res.status_code == 200
    return res.json()


def test_voice_act_gains_additive_ethos_suggestions(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        body = _voice_observation(
            client, sid,
            "Marco struggled to stay on task but showed courage during group reading",
        )
        assert body["intent"] == "observation"
        traits = [s["trait_id"] for s in body["ethos_suggestions"]]
        assert "bravery" in traits


def test_voice_act_existing_shape_survives_a_broken_taxonomy(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _break_ethos(tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        body = _voice_observation(
            client, sid,
            "Marco struggled to stay on task during group reading",
        )
        # Existing contract fields unchanged (frozen shape, hard rule 5).
        assert body["intent"] == "observation"
        assert body["action_taken"] == "saved"
        assert body["result"]["observation"]["student_id"] == sid
        assert isinstance(body["category_suggestions"], list)
        assert "Marco" in body["spoken_confirmation"]
        for key in ("tone_prefix", "gir_score", "match_quality",
                    "resolved_student", "routing_decision_ids"):
            assert key in body
        # Additive field degrades to [], never an error.
        assert body["ethos_suggestions"] == []


# ---------------------------------------------------------------------------
# 5. Gate regression: evidence enters the draft BEFORE the safety gates
# ---------------------------------------------------------------------------


def test_report_grade_evidence_appears_in_parent_draft(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        marker = "responded well to the visual vocabulary cards"
        assert _post_evidence(client, sid, summary=f"Student {marker} this week.").status_code == 200

        draft = client.post(
            "/api/parents/recommendation",
            json={"student_id": sid, "include_evidence_summaries": True},
        ).json()
        assert marker in draft["body"].lower()


def test_evidence_summaries_stay_out_of_draft_by_default(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        marker = "practiced the dialogue journal routine independently"
        _post_evidence(client, sid, summary=f"Student {marker}.")

        draft = client.post(
            "/api/parents/recommendation", json={"student_id": sid}
        ).json()
        assert marker not in draft["body"].lower()


def test_student_name_in_evidence_summary_is_flagged_for_review(monkeypatch, tmp_path):
    """THE gate-order regression: evidence text must enter the draft BEFORE
    `_strip_parent_output` + `check_publication_safety`, so a student name
    smuggled in via an evidence summary is caught exactly like a name in
    the generated prose. Lowercase name: the case-sensitive stripper
    misses it, the lowercasing gate must not."""
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client, "Marco Bianchi")
        res = _post_evidence(
            client, sid,
            summary="today marco bianchi showed real persistence during silent reading",
        )
        assert res.status_code == 200

        draft = client.post(
            "/api/parents/recommendation",
            json={"student_id": sid, "include_evidence_summaries": True},
        ).json()

        assert draft["review_required"] is True
        rules = [violation["rule"] for violation in draft["safety_warnings"]]
        assert "privacy_rules.student_data" in rules
        # Flag, never block: the offending text stays visible for the teacher.
        assert "persistence during silent reading" in draft["body"].lower()


def test_model_suggested_evidence_never_reaches_the_parent_draft(monkeypatch, tmp_path):
    """Only REPORT_GRADE_CONFIDENCE (teacher_confirmed / imported_verified)
    evidence may appear in a parent draft."""
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        marker = "guessed at unfamiliar words without decoding support"
        _post_evidence(
            client, sid,
            summary=f"Student {marker}.",
            confidence_level="model_suggested",
        )

        draft = client.post(
            "/api/parents/recommendation",
            json={"student_id": sid, "include_evidence_summaries": True},
        ).json()
        assert marker not in draft["body"].lower()


def test_soft_deleted_evidence_never_reaches_the_parent_draft(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        marker = "read the whole paragraph without prompting"
        evidence_id = _post_evidence(client, sid, summary=f"Student {marker}.").json()["evidence_id"]
        client.delete(f"/api/students/{sid}/evidence/{evidence_id}")

        draft = client.post(
            "/api/parents/recommendation",
            json={"student_id": sid, "include_evidence_summaries": True},
        ).json()
        assert marker not in draft["body"].lower()


# ---------------------------------------------------------------------------
# 6. Privacy events written; ids only, never content
# ---------------------------------------------------------------------------


def test_privacy_events_carry_ids_never_content(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    with TestClient(app) as client:
        sid = _create_student(client)
        secret = "confided that mornings at home are hard"
        evidence_id = _post_evidence(client, sid, summary=f"Student {secret}.").json()["evidence_id"]
        client.delete(f"/api/students/{sid}/evidence/{evidence_id}")

        events = _privacy_events(tmp_path)
        types = [e.get("event_type") for e in events]
        assert "evidence_recorded" in types
        assert "evidence_deleted" in types
        blob = json.dumps(events).lower()
        assert secret not in blob
        assert "marco" not in blob
