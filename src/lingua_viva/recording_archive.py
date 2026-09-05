"""Link corrected, confirmed observations to retained private audio originals."""
import re
from src.lingua_viva.docpipe import vault
from src.lingua_viva.deliverables.store import save_snapshot


def validate_recordings(source_ids):
    if not isinstance(source_ids, list) or len(source_ids) > 20:
        raise ValueError('Expected up to twenty recording identifiers')
    result = []
    for source_id in source_ids:
        if not isinstance(source_id, str) or not re.fullmatch(r'SRC-IMPORT-[a-f0-9]{64}', source_id):
            raise ValueError('Invalid recording identifier')
        source = vault.get_source(source_id)
        if source.original_ext not in {'.webm', '.wav', '.mp3', '.m4a', '.ogg', '.mp4'}:
            raise ValueError('Source is not a recording')
        directory = (vault.vault_root() / 'sources' / source_id).resolve()
        original = (directory / ('original' + source.original_ext)).resolve()
        if original.parent != directory or not original.is_file():
            raise ValueError('Missing recording')
        if source_id not in result:
            result.append(source_id)
    return result


def save_recordings(source_ids, observation, teacher_id):
    return [save_snapshot('observation_recording', 'Recorded observation',
            {'source_id': source_id, 'observation_id': observation.get('observation_id'),
             'student_id': observation.get('student_id'), 'printable_text': observation.get('raw_transcript', '')},
            teacher_id=teacher_id) for source_id in source_ids]
