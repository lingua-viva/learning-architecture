"""Synthetic pixels, actual local OCR; no classroom photos or network calls."""
from io import BytesIO
import pytest


def test_actual_ocr_reads_synthetic_english_and_italian(monkeypatch):
    pytest.importorskip('rapidocr_onnxruntime')
    from PIL import Image, ImageDraw, ImageFont
    from pathlib import Path
    candidates = [Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    font_path = next((p for p in candidates if p.exists()), None)
    font = ImageFont.truetype(str(font_path), 36) if font_path else ImageFont.load_default(size=36)
    picture = Image.new('RGB', (1200, 280), 'white')
    draw = ImageDraw.Draw(picture)
    draw.text((30, 35), 'I walked to school with my friend.', fill='black', font=font)
    draw.text((30, 115), 'Sono andato a scuola con un amico.', fill='black', font=font)
    stream = BytesIO(); picture.save(stream, format='PNG')
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('OCR attempted network access'))
    from src.lingua_viva.local_ocr import read_image
    result = read_image(stream.getvalue())
    assert 'school' in result['text'], result
    assert 'scuola' in result['text'], result
    assert result['requires_correction'] is True
    assert all(0 <= row['confidence'] <= 1 for row in result['ocr_lines'])
