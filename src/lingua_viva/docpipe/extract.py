from __future__ import annotations

from .contracts import ExtractionRecord, SourceRecord
from .model import ModelClient


async def extract_document(
    source: SourceRecord,
    content: bytes,
    *,
    model_client: ModelClient | None = None,
) -> ExtractionRecord:
    raise NotImplementedError("T3 implements grounded document extraction")

