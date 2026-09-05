"""Original Observe audio must survive transcription and lens confirmation."""
from fastapi.testclient import TestClient


def test_recording_survives_and_reopens_with_confirmed_observation(tmp_path, monkeypatch):
    monkeypatch.setenv('LV_STATE_HOME', str(tmp_path))
    monkeypatch.setenv('LV_CONFIG_HOME', str(tmp_path))
    from src.education.student_lens import StudentLensStore
    with StudentLensStore() as store:
        store.create_lens(student_id='demo-audio', display_name='Demo Learner')
    from src.lingua_viva import voice_stt
    class Speech:
        def transcribe(self, audio):
            return 'Explains ideas clearly to a partner.'
    monkeypatch.setattr(voice_stt, 'get_stt_provider', lambda: Speech())
    from src.web import app
    client = TestClient(app)
    audio = b'synthetic audio bytes: decoding is covered by the real Whisper journey'
    speech = client.post('/api/voice/stt', content=audio)
    assert speech.status_code == 200
    source_id = speech.json()['source_id']
    saved = client.post('/api/observe/capture', json={'student_id':'demo-audio',
        'transcript': speech.json()['transcript'], 'source_ids':[source_id]})
    assert saved.status_code == 200, saved.text
    snapshot = saved.json()['saved_recordings'][0]
    reopened = client.get('/api/artifacts/saved/' + snapshot['id'])
    assert reopened.json()['payload']['observation_id'] == saved.json()['observation']['observation_id']
    original = client.get('/api/artifacts/saved/' + snapshot['id'] + '/original')
    assert original.content == audio
    restricted = client.post('/api/observe/capture', json={'student_id':'demo-audio',
        'transcript': 'The child disclosed sexual abuse at home.', 'source_ids':[source_id]})
    assert restricted.json()['restricted'] is True
    assert 'saved_recordings' not in restricted.json()


def test_recording_disk_failure_refuses_transcription(tmp_path, monkeypatch):
    monkeypatch.setenv('LV_STATE_HOME', str(tmp_path))
    monkeypatch.setenv('LV_CONFIG_HOME', str(tmp_path))
    from src.lingua_viva.docpipe import lens_extract
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(lens_extract, 'preserve_import_source', fail)
    from src.web import app
    response = TestClient(app).post('/api/voice/stt', content=b'voice')
    assert response.status_code == 503
    assert response.json()['error'] == 'recording_not_saved'
