"""A family report must reach the coordinator, not merely claim it was routed."""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize('signal', ['The child disclosed sexual abuse at home.', 'Il bambino ha subito abuso sessuale.'])
def test_family_report_reaches_restricted_inbox_without_normal_log_text(tmp_path, monkeypatch, signal):
    monkeypatch.setenv('LV_CONFIG_HOME', str(tmp_path))
    monkeypatch.setenv('LV_STATE_HOME', str(tmp_path))
    from src.education.student_lens import StudentLensStore
    with StudentLensStore() as store:
        store.create_lens(student_id='family-demo', display_name='Demo Student')
    from src.lingua_viva import reasoning
    monkeypatch.setattr(reasoning, 'ReasoningEngine', lambda: None)
    from src.web import app
    client = TestClient(app)
    content = ('Demo Student\n\n' + signal).encode()
    response = client.post('/api/students/import-document', files={'file': ('family-report.txt', content)})
    assert response.status_code == 200, response.text
    from src.lingua_viva.safeguarding import read_restricted, pending_notifications
    entries = read_restricted('coordinator')
    assert len(entries) == 1
    assert signal in entries[0]['raw_transcript']
    assert entries[0]['student_id'] == 'family-demo'
    assert len(pending_notifications()) == 1
    assert signal not in json.dumps(response.json(), ensure_ascii=False)
    logs = list((tmp_path / 'imports').glob('*.ndjson'))
    assert logs
    assert all(signal not in p.read_text(encoding='utf-8') for p in logs)
    assert read_restricted('teacher') == []
    again = client.post('/api/students/import-document', files={'file': ('family-report.txt', content)})
    assert again.status_code == 200
    assert len(read_restricted('coordinator')) == 1
    assert len(pending_notifications()) == 1
