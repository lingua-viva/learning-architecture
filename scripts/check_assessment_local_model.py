"""Measure the actual local diagnostic model on synthetic English/Italian work."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run():
    from src.lingua_viva.assessment import analyse
    samples = ['Yesterday I go to the park. My friend were happy. We played with a ball.',
               'Ieri io andare al parco. Il mio amico erano felice. Abbiamo giocato con una palla.']
    for language, text in zip(('en', 'it'), samples):
        result = await analyse(text, source_id='SRC-synthetic', kind='written', language=language)
        print(language, result['generation_status'], result['dimensions'], flush=True)
        assert result['generation_status'] == 'local_model_suggestions', 'No acceptable local diagnostic was produced'
        assert all(item['quote'] in text for item in result['dimensions'].values())


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='lv-model-check-') as temporary:
        for key in ('LV_STATE_HOME', 'LV_CONFIG_HOME', 'LV_UPDATE_HOME'):
            os.environ[key] = temporary
        os.environ['LV_STUDENT_DB_PATH'] = str(Path(temporary) / 'students.db')
        asyncio.run(run())
