"""One diagnostic record for oral/written work; no grades, no silent replacement."""
import copy
import pytest
from src.education.student_lens import StudentLensStore
from src.lingua_viva.data_in_contracts import ExtractedField, ExtractionResult
from src.lingua_viva.student_lens_writer import write_student_lens


def diagnostic():
    text = 'I walked to school. Ho camminato fino a scuola.'
    return {'assessment_id': 'ASSESS-demo1', 'kind': 'written', 'source_id': 'SRC-demo',
            'transcript': text, 'language': 'it',
            'dimensions': {name: {'note': 'Teacher reviewed this sample.', 'quote': text,
                                  'needs_support': None} for name in ('fluency', 'syntax', 'grammar', 'vocabulary')}}


def test_diagnostic_requires_confirmation_and_survives_reopen(tmp_path):
    path = tmp_path / 'lens.db'
    value = diagnostic()
    result = ExtractionResult('student_lens', [ExtractedField('assessment_record', value, 1, ['SRC-demo'], 'needs_confirmation')], [], ['work.txt'])
    with StudentLensStore(db_path=path) as store:
        store.create_lens(student_id='demo', display_name='Demo Student')
        pending = write_student_lens(result, store=store, hint={'student_id': 'demo'}, source_kind='assessment')
        assert pending['review_required'] == ['assessment_record']
        assert store.export_lens('demo')['assessment_profile'] == []
        written = write_student_lens(result, store=store, hint={'student_id': 'demo'}, source_kind='assessment', confirmed_fields=['assessment_record'])
        assert written['written_fields'] == ['assessment_record']
    with StudentLensStore(db_path=path) as store:
        lens = store.export_lens('demo')
        assert lens['assessment_profile'][0]['transcript'] == value['transcript']
        assert all(v is None for v in lens['cefr_snapshot'].values())
        store.append_assessment('demo', value, 'teacher')
        assert len(store.export_lens('demo')['assessment_profile']) == 1
        changed = copy.deepcopy(value)
        changed['dimensions']['grammar']['note'] = 'A different judgement'
        with pytest.raises(ValueError, match='revision'):
            store.append_assessment('demo', changed, 'teacher')


@pytest.mark.parametrize('fault', ['grade', 'fabricated_quote', 'missing_dimension'])
def test_diagnostic_validation_refuses_unsupported_shape(tmp_path, fault):
    value = diagnostic()
    if fault == 'grade':
        value['dimensions']['grammar']['grade'] = 8
    elif fault == 'fabricated_quote':
        value['dimensions']['grammar']['quote'] = 'A sentence not in this work'
    else:
        del value['dimensions']['syntax']
    with StudentLensStore(db_path=tmp_path / 'lens.db') as store:
        store.create_lens(student_id='demo', display_name='Demo Student')
        with pytest.raises(ValueError):
            store.append_assessment('demo', value, 'teacher')
        assert store.export_lens('demo')['assessment_profile'] == []
