"""Shared oral/written diagnostic data. A teacher judgement is never a grade."""
from __future__ import annotations
import re
import json

DIMENSIONS = ('fluency', 'syntax', 'grammar', 'vocabulary')


def validate_assessment(value, _bound=None):
    if not isinstance(value, dict):
        return 'The assessment must be a structured record.'
    allowed = {'assessment_id', 'kind', 'source_id', 'transcript', 'language', 'dimensions',
               'metrics', 'generation_status', 'duration_seconds', 'original_source_id', 'segments'}
    if set(value) - allowed:
        return 'The assessment contains undeclared fields; grades are not accepted.'
    def contains_grade(item):
        if isinstance(item, dict):
            return any(str(key).lower() in {'grade', 'score', 'mark', 'cefr_estimate'} or contains_grade(child) for key, child in item.items())
        return isinstance(item, list) and any(contains_grade(child) for child in item)
    if contains_grade(value):
        return 'Grades and automatic language levels are not accepted in diagnostics.'
    if not re.fullmatch(r'ASSESS-[A-Za-z0-9-]{1,80}', str(value.get('assessment_id', ''))):
        return 'An assessment revision identifier is required.'
    if value.get('kind') not in {'oral', 'written', 'document'}:
        return 'Choose oral, written or document work.'
    if not isinstance(value.get('source_id'), str) or not value['source_id']:
        return 'The original source reference is required.'
    text = value.get('transcript')
    if not isinstance(text, str) or not text.strip() or len(text) > 100000:
        return 'The corrected text is required (maximum 100,000 characters).'
    dimensions = value.get('dimensions')
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        return 'Review all four dimensions: fluency, syntax, grammar and vocabulary.'
    for name, item in dimensions.items():
        if not isinstance(item, dict) or set(item) != {'note', 'quote', 'needs_support'}:
            return f'{name}: provide a note, source quote and support decision; no grade.'
        if item['needs_support'] is not None and type(item['needs_support']) is not bool:
            return f'{name}: the support decision must be yes, no or not determined.'
        if not isinstance(item['note'], str) or not item['note'].strip() or len(item['note']) > 4000:
            return f'{name}: a review note is required.'
        if not isinstance(item['quote'], str) or not item['quote'].strip() or item['quote'] not in text:
            return f'{name}: the evidence quote must occur in the corrected text.'
    from src.lingua_viva.docpipe.lens_extract import _is_red_safeguarding
    if _is_red_safeguarding(json.dumps(value, ensure_ascii=False)):
        return 'Restricted content belongs in coordinator review, not an assessment lens.'
    return None
