"""Bundled local OCR with confidence and mandatory teacher correction.

RapidOCR 1.4.4 ships its ONNX models in the wheel. Only in-memory pixels are
passed to it, never a URL. Confidence is an OCR estimate, not verified accuracy.
"""
from __future__ import annotations
from io import BytesIO
import threading

_engine = None
_lock = threading.Lock()
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp'}


def read_image(content: bytes) -> dict:
    global _engine
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise RuntimeError('Local photo reading is not installed. Run setup again, or paste corrected text from the original.')
    from PIL import Image, ImageOps
    import numpy as np
    with Image.open(BytesIO(content)) as original:
        if original.width * original.height > 40000000:
            raise RuntimeError('This photo is too large to read safely. Resize it below 40 megapixels.')
        pixels = np.asarray(ImageOps.exif_transpose(original).convert('RGB'))
    with _lock:
        if _engine is None:
            _engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        # EXIF has already oriented the page. The bundled angle classifier
        # flipped an upright Italian fixture upside down on Linux.
        rows, _ = _engine(pixels, text_score=0.1, use_cls=False)
    lines = [{'text': str(row[1]), 'confidence': float(row[2])} for row in (rows or [])]
    return {'text': '\n'.join(line['text'] for line in lines), 'ocr_lines': lines,
            'low_confidence': not lines or any(line['confidence'] < 0.85 for line in lines),
            'requires_correction': True}


def read_scanned_pdf(content: bytes) -> dict:
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(content)
    lines = []
    try:
        if len(document) > 10:
            raise RuntimeError('Choose up to ten scanned pages at a time.')
        for index in range(len(document)):
            page = document[index]
            bitmap = None
            try:
                bitmap = page.render(scale=2)
                stream = BytesIO()
                bitmap.to_pil().save(stream, format='PNG')
                read = read_image(stream.getvalue())
                lines.extend({**line, 'page': index + 1} for line in read['ocr_lines'])
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
    finally:
        document.close()
    return {'text': '\n'.join(line['text'] for line in lines), 'ocr_lines': lines,
            'low_confidence': not lines or any(line['confidence'] < 0.85 for line in lines),
            'requires_correction': True}
