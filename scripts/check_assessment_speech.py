"""Actual multilingual Whisper decoding, measured against synthetic fixture text."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def words(text):
    return re.findall(r"\b\w+\b", text.lower())


def wer(reference, actual):
    expected, actual = words(reference), words(actual)
    row = list(range(len(actual) + 1))
    for i, word in enumerate(expected, 1):
        next_row = [i]
        for j, other in enumerate(actual, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j-1] + (word != other)))
        row = next_row
    return row[-1] / max(len(expected), 1)


if __name__ == '__main__':
    from src.lingua_viva.voice_stt import get_stt_provider
    provider = get_stt_provider('small')
    base = Path(__file__).resolve().parents[1] / 'tests/fixtures/assessment'
    for language in ('en', 'it'):
        audio = (base / f'synthetic-{language}.wav').read_bytes()
        result = provider.transcribe_detailed(audio, language=language)
        error = wer((base / f'synthetic-{language}.txt').read_text(encoding='utf-8'), result['text'])
        print(f'{language}: duration={result["duration_seconds"]:.1f}s WER={error:.3f} spans={len(result["segments"])}', flush=True)
        print(result['text'], flush=True)
        assert error < 0.35, 'Synthetic speech transcription exceeded the test error threshold'
