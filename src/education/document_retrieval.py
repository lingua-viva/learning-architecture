"""
Document Retrieval — ontology-scoped semantic search over parsed documents.

Ontology-scoped, not always-on: `src/pipeline.py` is the shared 8-step
pipeline every domain in this repo runs through (legal, medical, education,
etc.). A `DocumentRetriever` is injected into `Pipeline` as an optional,
duck-typed dependency (same pattern as `ontology`/`memory`/`knowledge`) so
the core pipeline never imports anything from `src/education` — document
retrieval only activates for domains it was explicitly configured to serve,
and costs nothing (no embedding call, no store lookup) for every other
domain's queries running through the same shared pipeline.

Degrades to no document context, not a pipeline failure: if the local
Ollama embedding endpoint is down, `retrieve()` returns an empty list
rather than raising — a governed query should still complete (using
whatever Knowledge Library / research context it has) even if the local
document store happens to be unreachable at that moment.
"""

from __future__ import annotations

from src.education.document_store import DocumentStore, EmbeddingUnavailableError


class DocumentRetriever:
    """
    Wraps a DocumentStore and gates retrieval by classified domain.

    Usage:
        store = DocumentStore("~/.lingua-viva/runtime/documents.db")
        retriever = DocumentRetriever(store)  # defaults to the 9 education subdomains
        pipeline = Pipeline(document_retriever=retriever)

    Note: this ontology fork has no single "education" domain string — each
    `ontology/education/*.yaml` file declares its own domain (curriculum,
    assessment, planning, learner, parent, teacher, student, admin,
    infrastructure). The default set below is every education subdomain, so
    a caller doesn't have to enumerate them; pass an explicit `domains` set
    to narrow retrieval (e.g. only `curriculum`/`assessment` for a subject
    guide store).
    """

    EDUCATION_DOMAINS = {
        "curriculum", "assessment", "planning", "learner",
        "parent", "teacher", "student", "admin", "infrastructure",
    }

    def __init__(self, store: DocumentStore, domains: set[str] | None = None):
        self.store = store
        self.domains = domains or set(self.EDUCATION_DOMAINS)

    def retrieve(self, query: str, domain: str, k: int = 3) -> list[dict]:
        if domain not in self.domains:
            return []
        try:
            return self.store.search(query, k=k)
        except EmbeddingUnavailableError:
            return []
