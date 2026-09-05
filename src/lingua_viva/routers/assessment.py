"""Assess: original -> corrected text -> diagnostic review -> lens -> saved output."""
from __future__ import annotations
import asyncio
import hashlib
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from src.lingua_viva.access_roles import require_role, effective_teacher_id
from src.education.student_lens import StudentLensStore

router = APIRouter(prefix="/api/assess")


def _gate(request):
    return require_role(request, {'teacher'})


def _restricted(text, student_id, teacher_id, source_key):
    from src.lingua_viva.docpipe.lens_extract import _is_red_safeguarding
    if not _is_red_safeguarding(text):
        return None
    from src.lingua_viva.safeguarding import record_restricted_input
    record_restricted_input(student_id=student_id, teacher_id=teacher_id, text=text,
                            source_key=source_key, kind='assessment')
    return JSONResponse({'error': 'restricted_input', 'message': 'This input requires coordinator review. It was kept in the restricted local inbox and was not added to the lens.'}, status_code=409)


def _known_student(student_id):
    with StudentLensStore() as store:
        try:
            store.get_lens(student_id)
        except Exception:
            raise HTTPException(404, 'Choose an existing student.')


@router.post("/source")
async def source(request: Request):
    refusal = _gate(request)
    if refusal is not None:
        return refusal
    form = await request.form()
    student_id = str(form.get('student_id') or '')
    _known_student(student_id)
    upload = form.get('file')
    if upload is None or not getattr(upload, 'filename', None):
        raise HTTPException(400, 'Choose a recording or document.')
    content = await upload.read(50 * 1024 * 1024 + 1)
    if not content or len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, 'Choose a nonempty file up to 50 MB.')
    from src.lingua_viva.docpipe.lens_extract import preserve_import_source
    try:
        original = await asyncio.to_thread(preserve_import_source, content, upload.filename)
    except (OSError, ValueError):
        raise HTTPException(503, 'The original could not be saved. Check free disk space and retry.')
    extension = Path(upload.filename).suffix.lower()
    kind, duration, segments, ocr = 'written', None, [], {}
    try:
        if extension in {'.mp3', '.wav', '.m4a', '.webm', '.ogg', '.mp4'}:
            from src.lingua_viva.voice_stt import get_stt_provider
            provider = get_stt_provider('small')
            transcript = await asyncio.to_thread(provider.transcribe_detailed, content, language=str(form.get('language') or 'auto'))
            text = transcript['text']
            duration = transcript['duration_seconds']
            segments = transcript['segments']
            kind = 'oral'
        else:
            from src.lingua_viva.local_ocr import IMAGE_EXTENSIONS, read_image, read_scanned_pdf
            from src.lingua_viva.docpipe.extract import extract_plain_text
            if extension in IMAGE_EXTENSIONS:
                ocr = await asyncio.to_thread(read_image, content)
                text = ocr['text']
            else:
                try:
                    text = await asyncio.to_thread(extract_plain_text, content, extension)
                except Exception:
                    if extension != '.pdf':
                        raise
                    ocr = await asyncio.to_thread(read_scanned_pdf, content)
                    text = ocr['text']
    except RuntimeError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        raise HTTPException(422, 'The original is saved, but its text could not be read. Try a text document or a clear recording.')
    teacher_id = effective_teacher_id(request, 'local-teacher')
    refusal = _restricted(text, student_id, teacher_id, original.source_id)
    if refusal is not None:
        return refusal
    if not text.strip():
        raise HTTPException(422, 'No speech or readable text was found. The original is saved.')
    reading = {**ocr, 'source_id': original.source_id, 'text': text, 'kind': kind, 'duration_seconds': duration, 'segments': segments,
            'message': 'Correct the text before analysing. Nothing has been added to the lens.'}
    from src.lingua_viva.deliverables.store import save_snapshot
    try:
        reading['saved_reading'] = save_snapshot('source_reading', 'Source awaiting text correction',
                            {'student_id': student_id, 'source': dict(reading)}, teacher_id=teacher_id)
    except OSError:
        raise HTTPException(503, 'The original is retained, but its reading could not be saved. Check free disk space and retry.')
    return reading


@router.post("/analyse")
async def analyse_work(request: Request, payload: dict):
    refusal = _gate(request)
    if refusal is not None:
        return refusal
    student_id = str(payload.get('student_id') or '')
    _known_student(student_id)
    text = str(payload.get('text') or '').strip()
    if not text or len(text) > 100000 or payload.get('text_confirmed') is not True:
        raise HTTPException(422, 'Review and confirm the corrected text before analysing (maximum 100,000 characters).')
    duration = payload.get('duration_seconds')
    if duration is not None and (type(duration) not in (int, float) or not 2 <= duration <= 240):
        raise HTTPException(422, 'The recording duration must be between two seconds and four minutes.')
    if payload.get('kind', 'written') not in {'written', 'oral', 'document'}:
        raise HTTPException(422, 'Choose written, oral or document work.')
    teacher_id = effective_teacher_id(request, 'local-teacher')
    refusal = _restricted(text, student_id, teacher_id, hashlib.sha256(text.encode()).hexdigest())
    if refusal is not None:
        return refusal
    from src.lingua_viva.docpipe.lens_extract import preserve_import_source
    # Typed and corrected text is itself a retained source revision.
    try:
        original = preserve_import_source(text.encode(), 'corrected-assessment.txt')
    except (OSError, ValueError):
        raise HTTPException(503, 'The corrected text could not be saved. Check free disk space and retry.')
    from src.lingua_viva.assessment import analyse
    record = await analyse(text, source_id=original.source_id, kind=str(payload.get('kind') or 'written'),
                           language=str(payload.get('language') or 'auto'), duration_seconds=payload.get('duration_seconds'),
                           use_model=payload.get('use_model') is not False)
    record['original_source_id'] = payload.get('source_id')
    record['segments'] = payload.get('segments') or []
    from src.lingua_viva.assessment_data import validate_assessment
    invalid = validate_assessment(record)
    if invalid:
        raise HTTPException(422, invalid)
    from src.lingua_viva.deliverables.store import save_snapshot
    try:
        saved = save_snapshot('assessment_draft', 'Assessment awaiting review',
                              {'student_id': student_id, 'record': record, 'original_source_id': payload.get('source_id')}, teacher_id=teacher_id)
    except OSError:
        raise HTTPException(503, 'The diagnostic draft could not be saved. The corrected source is retained. Check free disk space and retry.')
    return {'record': record, 'saved_draft': saved, 'message': 'Review all four dimensions. No grade or CEFR level has been assigned.'}


@router.post("/confirm")
async def confirm_work(request: Request, payload: dict):
    refusal = _gate(request)
    if refusal is not None:
        return refusal
    student_id = str(payload.get('student_id') or '')
    _known_student(student_id)
    record = payload.get('record')
    if not isinstance(record, dict) or payload.get('confirmed') is not True:
        raise HTTPException(422, 'Review all dimensions and confirm the diagnostic first.')
    teacher_id = effective_teacher_id(request, 'local-teacher')
    from src.lingua_viva.assessment_data import validate_assessment
    text = str(record.get('transcript') or '')
    refusal = _restricted(text + '\n' + str(record.get('dimensions') or ''), student_id, teacher_id,
                          hashlib.sha256(text.encode()).hexdigest())
    if refusal is not None:
        return refusal
    invalid = validate_assessment(record)
    if invalid:
        raise HTTPException(422, invalid)
    from src.lingua_viva.docpipe import vault
    import re
    if not re.fullmatch(r'SRC-IMPORT-[a-f0-9]{64}', record['source_id']):
        raise HTTPException(422, 'The corrected source reference is invalid.')
    try:
        original = vault.get_source(record['source_id'])
        source_text = (vault.vault_root() / 'sources' / record['source_id'] / ('original' + original.original_ext)).read_text(encoding='utf-8')
    except (OSError, ValueError):
        raise HTTPException(422, 'The saved corrected source could not be read.')
    if source_text != text:
        raise HTTPException(422, 'The text changed after analysis. Analyse the corrected text again.')
    from src.lingua_viva.data_in_contracts import ExtractionResult, ExtractedField
    from src.lingua_viva.student_lens_writer import write_student_lens
    from src.lingua_viva.assessment import render_from_lens
    from src.lingua_viva.deliverables.store import save_snapshot
    with StudentLensStore() as store:
        result = write_student_lens(ExtractionResult('student_lens', [ExtractedField('assessment_record', record, 1,
                    [record['source_id']], 'needs_confirmation')], [], [record['source_id']]),
                    store=store, hint={'student_id': student_id}, teacher_id=teacher_id,
                    source_kind='assessment', confirmed_fields=['assessment_record'])
        if not result['written_fields']:
            return JSONResponse({'error': 'assessment_not_written', 'message': ' '.join(result['unresolved_questions'])}, status_code=422)
        rendered = render_from_lens(store.export_lens(student_id), record['assessment_id'])
    try:
        saved = save_snapshot('assessment', 'Reviewed language diagnostic', rendered, teacher_id=teacher_id)
    except OSError:
        raise HTTPException(503, 'The assessment is in the lens, but its printable file could not be saved. Retry to save the same revision.')
    return {**rendered, 'saved_deliverable': saved, 'accounting': result['accounting']}


@router.post("/withdraw")
async def withdraw(request: Request, payload: dict):
    refusal = _gate(request)
    if refusal is not None:
        return refusal
    with StudentLensStore() as store:
        try:
            store.withdraw_assessment(str(payload.get('student_id') or ''), str(payload.get('assessment_id') or ''),
                                      effective_teacher_id(request, 'local-teacher'))
        except ValueError as exc:
            raise HTTPException(404, str(exc))
    return {'withdrawn': True, 'message': 'Removed from the active lens. The saved version and original are preserved.'}
