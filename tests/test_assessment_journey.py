"""Text/document -> corrected sample -> review -> lens -> saved output -> undo."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('LV_STATE_HOME', str(tmp_path))
    monkeypatch.setenv('LV_CONFIG_HOME', str(tmp_path))
    from src.education.student_lens import StudentLensStore
    with StudentLensStore() as store:
        store.create_lens(student_id='assess-demo', display_name='Demo Student')
    from src.web import app
    return TestClient(app)


@pytest.mark.parametrize('text', ['I walked to school. I met my friend.', 'Sono andato a scuola. Ho incontrato un amico.'])
def test_shared_diagnostic_full_journey(client, text):
    source = client.post('/api/assess/source', files={'file': ('work.txt', text.encode())}, data={'student_id': 'assess-demo'})
    assert source.status_code == 200, source.text
    item = source.json()
    original = client.get('/api/artifacts/saved/' + item['saved_reading']['id'] + '/original')
    assert original.status_code == 200
    assert original.content == text.encode()
    analysed = client.post('/api/assess/analyse', json={'student_id': 'assess-demo', 'text': item['text'],
                           'source_id': item['source_id'], 'text_confirmed': True, 'use_model': False})
    assert analysed.status_code == 200, analysed.text
    record = analysed.json()['record']
    record['dimensions']['syntax']['needs_support'] = True
    record['dimensions']['syntax']['note'] = 'Practising complete sentences will help express ideas.'
    from src.education.student_lens import StudentLensStore
    with StudentLensStore() as store:
        assert store.export_lens('assess-demo')['assessment_profile'] == []
    response = client.post('/api/assess/confirm', json={'student_id': 'assess-demo', 'record': record, 'confirmed': True})
    assert response.status_code == 200, response.text
    assert text in response.json()['printable_text']
    assert response.json()['fields_used'] == ['assessment_profile']
    parent = client.post('/api/parents/recommendation', json={'student_id': 'assess-demo'})
    assert parent.status_code == 200
    assert 'Practising complete sentences' in parent.json()['body']
    assert parent.json()['minimum_evidence']['met'] is True
    saved = client.get('/api/artifacts/saved/' + response.json()['saved_deliverable']['id'])
    assert saved.status_code == 200
    assert saved.json()['payload']['printable_text'] == response.json()['printable_text']
    with StudentLensStore() as store:
        assert len(store.export_lens('assess-demo')['assessment_profile']) == 1
    removed = client.post('/api/assess/withdraw', json={'student_id': 'assess-demo', 'assessment_id': record['assessment_id']})
    assert removed.status_code == 200
    parent_after = client.post('/api/parents/recommendation', json={'student_id': 'assess-demo'})
    assert 'Practising complete sentences' not in parent_after.json()['body']
    with StudentLensStore() as store:
        assert store.export_lens('assess-demo')['assessment_profile'] == []
        assert store._conn.execute('SELECT count(*) FROM assessment_records').fetchone()[0] == 1


def test_no_analysis_without_review_and_no_red_in_saved_work(client):
    pending = client.post('/api/assess/analyse', json={'student_id': 'assess-demo', 'text': 'Some work'})
    assert pending.status_code == 422
    red = client.post('/api/assess/analyse', json={'student_id': 'assess-demo', 'text': 'Il bambino ha subito abuso sessuale.',
                                                'text_confirmed': True, 'use_model': False})
    assert red.status_code == 409
    assert 'abuso' not in red.text
    assert client.get('/api/artifacts/saved').json()['items'] == []
    from src.lingua_viva.safeguarding import read_restricted
    assert len(read_restricted('coordinator')) == 1


def test_confirm_rejects_text_changed_after_analysis(client):
    record = client.post('/api/assess/analyse', json={'student_id': 'assess-demo', 'text': 'I walk to school.',
                                                   'text_confirmed': True, 'use_model': False}).json()['record']
    record['transcript'] += ' And this was not saved.'
    result = client.post('/api/assess/confirm', json={'student_id': 'assess-demo', 'record': record, 'confirmed': True})
    assert result.status_code == 422


def test_assess_requires_authenticated_teacher_when_enabled(client, monkeypatch):
    monkeypatch.setenv('LV_AUTH_MODE', 'local_header')
    response = client.post('/api/assess/analyse', json={})
    assert response.status_code == 401
