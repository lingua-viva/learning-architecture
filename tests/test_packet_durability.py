"""Saved classroom materials are revisions, even within the same second."""
from tests.test_lesson_packet_routes import _payload
from src.education.content_differentiator import LessonInput


def test_same_second_packet_names_cannot_overwrite(monkeypatch):
    from src.lingua_viva import lesson_materials as lm
    class Clock:
        @staticmethod
        def now(*args):
            class Moment:
                def strftime(self, *args):
                    return '20260905-060000'
            return Moment()
    monkeypatch.setattr(lm, 'datetime', Clock)
    lesson = LessonInput(**_payload()['lesson'])
    assert lm.lesson_packet_filename(lesson) != lm.lesson_packet_filename(lesson)


def test_saved_materials_reopen_in_sources(tmp_path, monkeypatch):
    monkeypatch.setenv('LV_STATE_HOME', str(tmp_path))
    monkeypatch.setenv('LV_CONFIG_HOME', str(tmp_path))
    from src.web import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.post('/api/lesson-materials/packet/approve', json=_payload())
    assert response.status_code == 200, response.text
    saved = response.json()['saved_deliverable']
    reopened = client.get('/api/artifacts/saved/' + saved['id'])
    assert reopened.json()['payload']['print_html'] == response.json()['packet']['print_html']
