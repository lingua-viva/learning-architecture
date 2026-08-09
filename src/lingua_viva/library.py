"""
Per-machine knowledge library — the information-categorization spine.

Teachers drop local reference files (IB lesson catalogues, legal/safeguarding
reference docs, ADD/dyslexia support materials) into the library; each is
text-extracted, chunked, and classified against the repo's 111-node ontology
(ontology/engine.py — the same deterministic classifier the pipeline uses,
no LLM, no network) so the local model and UI can retrieve by category/role.

Layout (all under <LV_STATE_HOME>/library/ — same home-resolution convention
as src/lingua_viva/sources/ledger.py, so tests/conftest.py's hermetic
LV_STATE_HOME redirect covers this store too):

    library/index.ndjson          one JSON line per document (append-only)
    library/docs/<doc_id>/text.txt      full extracted text
    library/docs/<doc_id>/chunks.ndjson one JSON line per chunk (+ per-chunk
                                        classification)

Zero-egress: this module performs no network I/O. Ingest of external research
results happens only via add_research_result(), called by the fail-closed
perplexity_gateway — never by the pipeline.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt"}

# Chunking targets: paragraphs packed to ~1400 chars keeps a chunk within a
# single topic (signal matching degrades on multi-topic text) while staying
# large enough for the token-overlap search to have signal.
CHUNK_TARGET_CHARS = 1400
MAX_CHUNK_CHARS = 2800
MAX_CATEGORIES = 5
MAX_CLASSIFY_CHUNKS = 40  # cap classification work on very large documents

# Role filter: ontology education-pack domains grouped by the audience they
# serve. Docs default to "teacher" when no education domain matched (e.g. a
# legal/safeguarding reference classifying into core/legal domains is still
# teacher-facing material).
ROLE_DOMAINS: dict[str, frozenset[str]] = {
    "teacher": frozenset({"teacher", "curriculum", "planning", "assessment"}),
    "student": frozenset({"student", "learner"}),
    "parent": frozenset({"parent"}),
    "admin": frozenset({"admin", "infrastructure"}),
}

_WRITE_LOCK = threading.Lock()
_ENGINE = None
_ENGINE_LOCK = threading.Lock()

_TOKENIZE = re.compile(r"\w+")


# ── paths (LV_STATE_HOME convention, mirrors sources/ledger.py) ─────────────

def _state_root() -> Path:
    env = os.environ.get("LV_STATE_HOME", "").strip()
    return Path(env).expanduser() if env else Path.home() / ".lingua-viva"


def library_root() -> Path:
    return _state_root() / "library"


def index_path() -> Path:
    return library_root() / "index.ndjson"


def docs_dir() -> Path:
    return library_root() / "docs"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── ontology classifier (shared, deterministic, offline) ────────────────────

def _engine():
    """Process-wide OntologyEngine — YAML load is ~100 files, do it once."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            from ontology.engine import OntologyEngine

            _ENGINE = OntologyEngine()
        return _ENGINE


def reset_engine_for_tests() -> None:
    global _ENGINE
    with _ENGINE_LOCK:
        _ENGINE = None


# ── extraction ──────────────────────────────────────────────────────────────

def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber

        parts: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n\n".join(p for p in parts if p.strip())
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"unsupported file type: {suffix} (supported: pdf, md, txt)")


def chunk_text(text: str) -> list[str]:
    """Paragraph-preserving chunker: pack blank-line-separated paragraphs up
    to CHUNK_TARGET_CHARS; hard-split any single paragraph over MAX_CHUNK_CHARS."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        while len(para) > MAX_CHUNK_CHARS:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            chunks.append(para[:MAX_CHUNK_CHARS])
            para = para[MAX_CHUNK_CHARS:].strip()
        if not para:
            continue
        if current and current_len + len(para) > CHUNK_TARGET_CHARS:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(para)
        current_len += len(para) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


# ── classification ──────────────────────────────────────────────────────────

def classify_chunk(text: str, title: str = "") -> dict[str, Any]:
    """Classify one chunk. Title tokens are prepended — the filename/heading
    usually carries the strongest category signal on reference material."""
    query = f"{title}\n{text}"[:4000]
    result = _engine().classify(query)
    return {
        "node_id": result.riu_id,
        "name": result.name,
        "domain": result.domain,
        "confidence": round(float(result.confidence), 3),
    }


def aggregate_categories(chunk_categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Vote across per-chunk classifications → top document categories."""
    votes: dict[str, dict[str, Any]] = {}
    for cat in chunk_categories:
        node_id = cat["node_id"]
        entry = votes.setdefault(node_id, {
            "node_id": node_id, "name": cat["name"], "domain": cat["domain"],
            "votes": 0, "confidence_sum": 0.0,
        })
        entry["votes"] += 1
        entry["confidence_sum"] += float(cat.get("confidence", 0.0))
    total = max(1, len(chunk_categories))
    ranked = sorted(votes.values(), key=lambda e: (e["votes"], e["confidence_sum"]), reverse=True)
    return [
        {
            "node_id": e["node_id"],
            "name": e["name"],
            "domain": e["domain"],
            "score": round(e["votes"] / total, 3),
            "confidence": round(e["confidence_sum"] / e["votes"], 3),
        }
        for e in ranked[:MAX_CATEGORIES]
    ]


def roles_for_categories(categories: list[dict[str, Any]]) -> list[str]:
    roles: set[str] = set()
    for cat in categories:
        domain = str(cat.get("domain", ""))
        for role, domains in ROLE_DOMAINS.items():
            if domain in domains:
                roles.add(role)
    return sorted(roles) if roles else ["teacher"]


# ── persistence ─────────────────────────────────────────────────────────────

def _append_index_line(entry: dict[str, Any]) -> None:
    path = index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")


def load_index() -> list[dict[str, Any]]:
    path = index_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def get_document(doc_id: str) -> Optional[dict[str, Any]]:
    for entry in load_index():
        if entry.get("doc_id") == doc_id:
            return entry
    return None


def load_chunks(doc_id: str) -> list[dict[str, Any]]:
    path = docs_dir() / doc_id / "chunks.ndjson"
    if not path.exists():
        return []
    chunks: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            chunks.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return chunks


# ── ingest ──────────────────────────────────────────────────────────────────

def _derive_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return fallback


def _ingest_text(
    text: str,
    *,
    title: str,
    source: str,
    source_path: str,
) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("no extractable text")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

    with _WRITE_LOCK:
        for entry in load_index():
            if entry.get("sha256") == sha:
                return entry  # dedup: identical content already ingested

        doc_id = f"LIB-{sha[:16]}"
        chunks = chunk_text(text)
        chunk_records: list[dict[str, Any]] = []
        chunk_categories: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            record: dict[str, Any] = {"chunk_index": i, "text": chunk}
            if i < MAX_CLASSIFY_CHUNKS:
                cat = classify_chunk(chunk, title=title)
                record["category"] = cat
                chunk_categories.append(cat)
            chunk_records.append(record)

        categories = aggregate_categories(chunk_categories)
        roles = roles_for_categories(categories)

        doc_dir = docs_dir() / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "text.txt").write_text(text, encoding="utf-8")
        with open(doc_dir / "chunks.ndjson", "w", encoding="utf-8") as handle:
            for record in chunk_records:
                handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

        entry = {
            "doc_id": doc_id,
            "source_path": source_path,
            "sha256": sha,
            "title": title,
            "categories": categories,
            "roles": roles,
            "source": source,
            "ingested_at": now_iso(),
            "chunk_count": len(chunk_records),
            "text_chars": len(text),
        }
        _append_index_line(entry)
        return entry


def add_document(path: Path | str, *, title: Optional[str] = None) -> dict[str, Any]:
    """Ingest a local file into the library. Refuses private-data paths."""
    path = Path(path).expanduser()
    from src.lingua_viva.privacy import is_private_path

    if is_private_path(path):
        raise PermissionError(f"refused: {path} matches a private Lingua Viva data rule")
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported file type: {path.suffix} (supported: pdf, md, txt)")
    text = extract_text(path)
    return _ingest_text(
        text,
        title=title or _derive_title(text, path.stem),
        source="local",
        source_path=str(path.resolve()),
    )


def add_research_result(
    query: str,
    content: str,
    *,
    citations: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Store an external research result as a library document (source =
    'perplexity'). Called ONLY by perplexity_gateway after sanitization;
    results live in the library and flow nowhere else."""
    parts = [f"# Research: {query}", "", content.strip()]
    if citations:
        parts += ["", "## Citations"] + [f"- {c}" for c in citations]
    text = "\n".join(parts) + "\n"
    return _ingest_text(
        text,
        title=f"Research: {query}"[:120],
        source="perplexity",
        source_path=f"perplexity://{hashlib.sha256(query.encode('utf-8')).hexdigest()[:12]}",
    )


# ── retrieval ───────────────────────────────────────────────────────────────

def _category_matches(entry: dict[str, Any], category: str) -> bool:
    needle = category.strip().lower()
    for cat in entry.get("categories", []):
        if needle in {
            str(cat.get("node_id", "")).lower(),
            str(cat.get("domain", "")).lower(),
            str(cat.get("name", "")).lower(),
        }:
            return True
    return False


def search(
    query: Optional[str] = None,
    *,
    category: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search the library by free-text query and/or category, with an optional
    role filter. Query scoring is token overlap against chunks (deterministic,
    offline); without a query, matching docs are returned newest-first."""
    entries = load_index()
    if category:
        entries = [e for e in entries if _category_matches(e, category)]
    if role:
        wanted = role.strip().lower()
        entries = [e for e in entries if wanted in [r.lower() for r in e.get("roles", [])]]

    results: list[dict[str, Any]] = []
    query_tokens = set(_TOKENIZE.findall(query.lower())) if query else set()
    for entry in entries:
        best_score = 0.0
        best_chunk: Optional[dict[str, Any]] = None
        if query_tokens:
            title_tokens = set(_TOKENIZE.findall(str(entry.get("title", "")).lower()))
            title_score = len(query_tokens & title_tokens) / len(query_tokens)
            for chunk in load_chunks(entry["doc_id"]):
                chunk_tokens = set(_TOKENIZE.findall(chunk.get("text", "").lower()))
                score = len(query_tokens & chunk_tokens) / len(query_tokens)
                if score > best_score or best_chunk is None:
                    best_score, best_chunk = score, chunk
            best_score = max(best_score, title_score)
            if best_score <= 0.0:
                continue
        snippet = ""
        chunk_index = None
        if best_chunk is not None:
            snippet = best_chunk.get("text", "")[:240]
            chunk_index = best_chunk.get("chunk_index")
        results.append({
            "doc_id": entry["doc_id"],
            "title": entry.get("title", ""),
            "score": round(best_score, 3),
            "categories": entry.get("categories", []),
            "roles": entry.get("roles", []),
            "source": entry.get("source", "local"),
            "ingested_at": entry.get("ingested_at", ""),
            "snippet": snippet,
            "chunk_index": chunk_index,
        })

    if query_tokens:
        results.sort(key=lambda r: r["score"], reverse=True)
    else:
        results.sort(key=lambda r: r["ingested_at"], reverse=True)
    return results[: max(0, int(limit))]


def status() -> dict[str, Any]:
    entries = load_index()
    by_source: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    by_role: dict[str, int] = {}
    chunk_count = 0
    for entry in entries:
        by_source[entry.get("source", "local")] = by_source.get(entry.get("source", "local"), 0) + 1
        chunk_count += int(entry.get("chunk_count", 0))
        for cat in entry.get("categories", [])[:1]:  # primary category only
            domain = str(cat.get("domain", "unknown"))
            by_domain[domain] = by_domain.get(domain, 0) + 1
        for r in entry.get("roles", []):
            by_role[r] = by_role.get(r, 0) + 1
    return {
        "library_root": str(library_root()),
        "doc_count": len(entries),
        "chunk_count": chunk_count,
        "by_source": by_source,
        "by_primary_domain": by_domain,
        "by_role": by_role,
    }
