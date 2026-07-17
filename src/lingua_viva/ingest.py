from __future__ import annotations

from pathlib import Path


DOCUMENT_STORE_PATH = (
    Path(__file__).parents[2]
    / "case-studies" / "04-still-i-rise" / "data" / "documents.db"
)

ALLOWED_DOC_TYPES = {"curriculum", "organizational"}
BLOCKED_DOC_TYPES = {"student-records"}


def document_retriever():
    if not DOCUMENT_STORE_PATH.exists():
        return None
    from src.education.document_retrieval import DocumentRetriever
    from src.education.document_store import DocumentStore

    return DocumentRetriever(DocumentStore(DOCUMENT_STORE_PATH))


def ingest_document(path: Path, doc_type: str) -> dict:
    from src.education.document_parser import DocumentParser
    from src.education.document_store import DocumentStore, EmbeddingUnavailableError

    if doc_type in BLOCKED_DOC_TYPES:
        return {
            "ok": False,
            "reason": "blocked_type",
            "error": (
                f"Refused: document type '{doc_type}' is not supported by this ingestion path. "
                "Reason: PII redaction does not reliably catch bare student given names "
                "(no title prefix) — see src/education/document_parser.py module docstring."
            ),
        }
    if doc_type not in ALLOWED_DOC_TYPES:
        return {
            "ok": False,
            "reason": "unknown_type",
            "error": f"Unknown document type '{doc_type}'. Allowed: {', '.join(sorted(ALLOWED_DOC_TYPES))}",
        }

    parser = DocumentParser()
    try:
        chunks = parser.parse(path)
    except FileNotFoundError:
        return {"ok": False, "reason": "not_found", "error": f"Document not found: {path}"}
    except ValueError as exc:
        return {"ok": False, "reason": "unsupported_format", "error": str(exc)}
    except Exception:
        return {
            "ok": False,
            "reason": "parse_failed",
            "error": f"This file couldn't be read — try a different PDF ({path.name}).",
        }

    if not chunks:
        return {
            "ok": False,
            "reason": "empty",
            "error": f"No content extracted from {path.name} — nothing to ingest.",
        }

    store = DocumentStore(DOCUMENT_STORE_PATH)
    try:
        added = store.add_chunks(chunks)
    except EmbeddingUnavailableError as exc:
        return {"ok": False, "reason": "embedding_unavailable", "error": str(exc)}
    finally:
        store.close()

    total_redactions = sum(len(chunk.redactions) for chunk in chunks)
    needs_review = sum(1 for chunk in chunks if chunk.needs_review)
    tables = sum(1 for chunk in chunks if chunk.is_table)

    return {
        "ok": True,
        "filename": path.name,
        "chunks_added": added,
        "tables": tables,
        "prose": added - tables,
        "redactions": total_redactions,
        "needs_review": needs_review,
        "store": str(DOCUMENT_STORE_PATH),
    }
