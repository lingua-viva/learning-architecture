import pytest
from tests.test_assessment_journey import client


def test_admin_query_saves_reopenable_result_and_csv(client):
    result = client.post('/api/admin/lens-query/L1/save', json={})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body['result']['targets'] == 1
    assert 'Demo Student' not in body['csv']
    reopened = client.get('/api/artifacts/saved/' + body['saved_deliverable']['id'])
    assert reopened.json()['payload']['csv'] == body['csv']


def test_teacher_cannot_use_admin_query_when_roles_enabled(client, monkeypatch):
    monkeypatch.setenv('LV_AUTH_MODE', 'local_header')
    result = client.post('/api/admin/lens-query/L1/save', json={}, headers={
        'X-LV-User-Id': 'user', 'X-LV-Role': 'teacher', 'X-LV-Teacher-Id': 'teacher'})
    assert result.status_code == 403
