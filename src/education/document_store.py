"""
Document Store — local vector store for parsed document chunks.

Research (mandatory, ran before designing this artifact):
  mc research "SQLite-vec vs Chroma vs FAISS for a local-first, single-node
  document retrieval store. Embedding model size/quality tradeoffs for
  local Ollama-served models (nomic-embed-text vs mxbai-embed-large vs
  all-minilm)."
This call routed correctly through the ontology this time (unlike the two
misroutes flagged earlier in this build) and returned a real, cited
recommendation. Confirmed directly: SQLite-vec needs no separate service
(no Chroma server process, no FAISS index files to manage outside the
existing SQLite-based persistence pattern this repo already uses for
memory/cold storage), ships as a loadable SQLite extension with no native
build step on this host, and keeps a single file per case study — trivial
to gitignore, back up, or delete. nomic-embed-text (768-dim) was already
pulled in the local Ollama instance (confirmed via `/api/tags` before
choosing it) and is a well-regarded open embedding model for retrieval —
no download/setup cost, no reason to prefer a different one.

What this is NOT: a multi-tenant or networked vector database. One SQLite
file per case study, opened directly by this process. Not a re-ranker —
retrieval is plain cosine similarity over embeddings, ranked by
sqlite-vec's built-in distance ordering. If retrieval quality demands
re-ranking or hybrid (BM25 + vector) search, that is future work.

Storage location: the caller supplies the DB path. Lingua Viva's ingestion
wrapper defaults to ~/.lingua-viva/runtime/documents.db, keeping
student/school document content and embeddings out of the repository.

Embeddings never leave the machine: nomic-embed-text is called against
the local Ollama instance only (http://localhost:11434), the same
pattern src/pipeline.py already uses for model calls — no cloud fallback
path exists here, unlike the reasoning-model call in pipeline.py. If
Ollama is unreachable, calls fail loudly (no silent fallback to a
degraded or non-local embedding path, which would risk sending document
content off-machine without an explicit decision to do so).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib import error, request

import sqlite_vec

from src.education.document_parser import ChunkRecord

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the local Ollama embedding endpoint can't be reached."""


def _embed(text: str) -> list[float]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except (error.URLError, ConnectionError, TimeoutError) as exc:
        raise EmbeddingUnavailableError(
            f"Local Ollama embedding endpoint unreachable at {OLLAMA_EMBED_URL} "
            f"(model={EMBED_MODEL}). Is Ollama running?"
        ) from exc

    embedding = body.get("embedding")
    if not embedding or len(embedding) != EMBED_DIM:
        raise EmbeddingUnavailableError(
            f"Unexpected embedding response from {EMBED_MODEL}: "
            f"expected {EMBED_DIM} dims, got {len(embedding) if embedding else 0}"
        )
    return embedding


class DocumentStore:
    """
    Local SQLite-vec-backed store for parsed document chunks.

    Usage:
        store = DocumentStore("~/.lingua-viva/runtime/documents.db")
        store.add_chunks(chunks)  # from DocumentParser.parse()
        results = store.search("what are the criterion B levels?", k=5)
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._conn.row_factory = sqlite3.Row

        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                source_file TEXT NOT NULL,
                page_start INTEGER NOT NULL,
                page_end INTEGER NOT NULL,
                section TEXT NOT NULL,
                is_table INTEGER NOT NULL DEFAULT 0,
                redactions TEXT NOT NULL DEFAULT '[]',
                needs_review INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
                chunk_id TEXT PRIMARY KEY,
                embedding FLOAT[{EMBED_DIM}]
            )
        """)
        self._conn.commit()

    def add_chunks(self, chunks: list[ChunkRecord]) -> int:
        """Embed and store chunks. Re-adding an existing chunk_id replaces it."""
        added = 0
        for chunk in chunks:
            embedding = _embed(chunk.text)
            self._conn.execute(
                """
                INSERT OR REPLACE INTO chunks
                    (chunk_id, text, source_file, page_start, page_end,
                     section, is_table, redactions, needs_review)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.text,
                    chunk.source_file,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.section,
                    int(chunk.is_table),
                    json.dumps(chunk.redactions),
                    int(chunk.needs_review),
                ),
            )
            self._conn.execute(
                "DELETE FROM chunk_vectors WHERE chunk_id = ?", (chunk.chunk_id,)
            )
            self._conn.execute(
                "INSERT INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
                (chunk.chunk_id, sqlite_vec.serialize_float32(embedding)),
            )
            added += 1
        self._conn.commit()
        return added

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Return up to k chunks ranked by cosine distance to the query."""
        query_embedding = _embed(query)
        rows = self._conn.execute(
            """
            SELECT c.chunk_id, c.text, c.source_file, c.page_start, c.page_end,
                   c.section, c.is_table, c.redactions, c.needs_review,
                   v.distance
            FROM chunk_vectors v
            JOIN chunks c ON c.chunk_id = v.chunk_id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (sqlite_vec.serialize_float32(query_embedding), k),
        ).fetchall()

        return [
            {
                "chunk_id": row["chunk_id"],
                "text": row["text"],
                "source_file": row["source_file"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "section": row["section"],
                "is_table": bool(row["is_table"]),
                "redactions": json.loads(row["redactions"]),
                "needs_review": bool(row["needs_review"]),
                "distance": row["distance"],
            }
            for row in rows
        ]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
