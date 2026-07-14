"""
Mission Canvas API Server

HTTP API that wraps the governed pipeline. The hub (server.mjs) calls this.
The browser calls the hub. The pipeline does the thinking.

Endpoints:
    POST /api/query      — run a query through the full pipeline
    GET  /api/health      — health check
    GET  /api/stats       — compounding metrics
    GET  /api/classify    — classify only (no reasoning)

Every endpoint returns JSON. The pipeline's gates, classification,
knowledge retrieval, and memory all fire on every query.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import Pipeline
from ontology.engine import OntologyEngine
from knowledge import KnowledgeStore
from memory.store import MemoryStore


# Shared instances — initialized once, reused across requests
_pipeline: Optional[Pipeline] = None
_engine: Optional[OntologyEngine] = None
_knowledge: Optional[KnowledgeStore] = None
_memory: Optional[MemoryStore] = None


def _init():
    global _pipeline, _engine, _knowledge, _memory
    if _pipeline is None:
        _engine = OntologyEngine()
        _knowledge = KnowledgeStore()
        _knowledge.set_ontology(_engine)
        _memory = MemoryStore()
        _pipeline = Pipeline(
            ontology=_engine,
            memory=_memory,
            knowledge=_knowledge,
        )


class MCHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Mission Canvas API."""

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/query":
            self._handle_query()
        elif path == "/api/classify":
            self._handle_classify()
        else:
            self._send_json(404, {"error": "not found"})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/health":
            self._handle_health()
        elif path == "/api/stats":
            self._handle_stats()
        else:
            self._send_json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _handle_query(self):
        """Run a query through the full governed pipeline."""
        _init()
        body = self._read_body()
        if not body:
            self._send_json(400, {"error": "missing request body"})
            return

        query = body.get("query", "")
        intent = body.get("intent")
        session_id = body.get("session_id")

        if not query:
            self._send_json(400, {"error": "missing 'query' field"})
            return

        try:
            result = asyncio.run(_pipeline.run(query, intent=intent, session_id=session_id))
            self._send_json(200, {
                "classification": {
                    "node": result.classification.riu_id,
                    "name": result.classification.name,
                    "domain": result.classification.domain,
                    "confidence": result.classification.confidence,
                    "signals": result.classification.signals_matched,
                    "blocks_external": result.classification.blocks_external,
                },
                "result": {
                    "content": result.synthesis.content,
                    "confidence": result.path_record.confidence_at_exit,
                    "citations": result.synthesis.citations,
                    "intent": result.classification.default_intent,
                },
                "pipeline": {
                    "steps": result.steps_executed,
                    "external_called": result.external_called,
                    "duration_ms": result.duration_ms,
                    "gap_signals": result.gap_signals,
                    "lens_applied": result.path_record.lens_applied,
                    "knowledge_used": result.path_record.knowledge_entries_used,
                },
                "session_id": result.session_id,
            })
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_classify(self):
        """Classify only — no reasoning, no external calls."""
        _init()
        body = self._read_body()
        query = body.get("query", "") if body else ""
        if not query:
            self._send_json(400, {"error": "missing 'query' field"})
            return

        result = _engine.classify(query, body.get("intent"))
        self._send_json(200, {
            "node": result.riu_id,
            "name": result.name,
            "domain": result.domain,
            "confidence": result.confidence,
            "signals": result.signals_matched,
            "blocks_external": result.blocks_external,
            "intent": result.default_intent,
            "co_occurring": result.co_occurring,
        })

    def _handle_health(self):
        """Return health check results."""
        _init()
        from src.integrity.health_check import HealthCheck
        hc = HealthCheck()
        result = hc.run()
        self._send_json(200, {
            "score": result.score,
            "checks_passed": result.checks_passed,
            "checks_total": result.checks_total,
            "healthy": result.healthy,
            "sections": result.sections,
        })

    def _handle_stats(self):
        """Return compounding metrics."""
        _init()
        self._send_json(200, {
            "ontology_nodes": _engine.node_count,
            "domains": _engine.domain_count,
            "knowledge_entries": _knowledge.entry_count,
            "citations": _knowledge.citation_count,
            "path_records": _memory.total_path_count(),
            "gap_signals": _memory.gap_signal_count(),
            "redis_connected": _memory.redis_connected(),
        })

    def _read_body(self, max_bytes: int = 10_000_000) -> Optional[dict]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        if length > max_bytes:
            return None  # Reject oversized payloads
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            return None

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        # Quieter logging
        pass


def serve(port: int = 7896):
    """Start the API server."""
    _init()
    server = HTTPServer(("127.0.0.1", port), MCHandler)
    print(f"Mission Canvas API: http://127.0.0.1:{port}")
    print(f"  POST /api/query     — run governed pipeline")
    print(f"  POST /api/classify  — classify only")
    print(f"  GET  /api/health    — health check")
    print(f"  GET  /api/stats     — compounding metrics")
    server.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7896
    serve(port)
