"""Operator 5 September: approved work must survive closing/updating the app."""
import json
from pathlib import Path

from tests.test_u10_approve_print import client, evidenced_lens, STUDENT


def test_approved_notes_are_separate_reopenable_files(client, evidenced_lens):
    first = client.post('/api/parents/approve', json={
        'student_id': STUDENT, 'body': 'Your child explains her thinking to a partner.',
    })
    assert first.status_code == 200, first.text
    saved = first.json()['saved_deliverable']
    original = Path(saved['path']).read_bytes()
    second = client.post('/api/parents/approve', json={
        'student_id': STUDENT, 'body': 'Your child explains her thinking before writing.',
    })
    assert second.status_code == 200, second.text
    assert second.json()['saved_deliverable']['id'] != saved['id']
    assert Path(saved['path']).read_bytes() == original
    assert json.loads(original)['payload']['printable_text'] == first.json()['printable_text']
    listing = client.get('/api/artifacts/saved').json()
    assert saved['id'] in [r['id'] for r in listing['items']]
    reopened = client.get('/api/artifacts/saved/' + saved['id'])
    assert reopened.status_code == 200
    assert reopened.json()['payload']['printable_text'] == first.json()['printable_text']


def test_disk_failure_cannot_claim_approval_was_saved(client, evidenced_lens, monkeypatch):
    from src.lingua_viva.deliverables import store
    def fail(*args, **kwargs):
        raise OSError('private system path')
    monkeypatch.setattr(store, 'save_snapshot', fail)
    response = client.post('/api/parents/approve', json={'student_id': STUDENT})
    assert response.status_code == 503
    assert response.json()['error'] == 'deliverable_not_saved'
    assert 'private system path' not in response.text
