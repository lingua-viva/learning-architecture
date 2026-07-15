"""
Mission Canvas CLI — Intent Dispatcher

Usage:
    mc protect "Is this privileged?"
    mc research "Delaware fiduciary duty cases"
    mc decide "Should we settle or litigate?"
    mc create "Draft a client update memo"
    mc diagnose "Why did the query route externally?"
    mc reflect "What patterns are emerging?"
    mc health                   # Run health check
    mc stats                    # Show compounding metrics
    mc candidates               # List candidate RIUs (ontology gaps)
    mc evaluate <id>            # Evaluate a candidate for promotion
    mc codex task <intent> "..." # Generate governed Codex task envelope
    mc codex result <task_id> <json-file> # Store Codex result envelope
    mc codex history [query]    # Show Codex execution audit records
    mc ingest <path.pdf> --type=curriculum|organizational  # Ingest a document
"""

import asyncio
import os
import sys
import time
import json
from pathlib import Path

# Ensure mission-canvas root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ontology.engine import OntologyEngine
from memory.store import MemoryStore
from knowledge import KnowledgeStore
from src.pipeline import Pipeline
from src.session import get_active_session, start_session, end_session, session_status, increment_session


INTENTS = {
    "protect": "PROTECT",
    "research": "RESEARCH",
    "decide": "DECIDE",
    "create": "CREATE",
    "diagnose": "DIAGNOSE",
    "reflect": "REFLECT",
}

# Governed RAG: the local document store for ingested education documents.
# Path convention matches case-studies/04-still-i-rise/.gitignore's `data/`
# entry — no ingested document content or embeddings are ever committed.
DOCUMENT_STORE_PATH = (
    Path(__file__).parent.parent
    / "case-studies" / "04-still-i-rise" / "data" / "documents.db"
)

# Restriction enforced HERE, not in DocumentParser: its Layer 2 person-name
# pattern requires a title prefix ("Dr. Smith") and will not reliably catch
# a bare given name ("Amina") with no surrounding context — exactly the
# shape of raw student-record data. See src/education/document_parser.py
# module docstring for the full reasoning.
ALLOWED_DOC_TYPES = {"curriculum", "organizational"}
BLOCKED_DOC_TYPES = {"student-records"}


def _document_retriever():
    """
    Build a DocumentRetriever bound to the store, if anything has been
    ingested yet. Returns None (not an empty store) when no ingestion has
    happened — avoids creating an empty SQLite file as a side effect of
    every ordinary query, and avoids paying an embedding-call cost on
    every query for a store that would return nothing anyway.
    """
    if not DOCUMENT_STORE_PATH.exists():
        return None
    from src.education.document_store import DocumentStore
    from src.education.document_retrieval import DocumentRetriever
    return DocumentRetriever(DocumentStore(DOCUMENT_STORE_PATH))


def ingest_document(path: Path, doc_type: str) -> dict:
    """
    Core ingestion logic: validate doc_type, parse, redact, and store a PDF
    in the education document store. Returns a structured result dict
    instead of printing, so it has exactly one caller-agnostic behavior.

    Shared by the CLI (`run_ingest`, below) and the web upload route
    (`POST /api/ingest` in src/web.py, Gap 2 of
    case-studies/04-still-i-rise/SPEC_ONE_CLICK_LOCAL_APP_2026-07-14.md) —
    both paths get identical validation, redaction, and storage behavior;
    only the presentation (print vs JSON) differs at the caller.
    """
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
        # Raised by DocumentParser.parse() for any non-.pdf suffix.
        return {"ok": False, "reason": "unsupported_format", "error": str(exc)}
    except Exception:
        # Corrupt PDF, scanned-image-only PDF with no extractable text, or
        # any other pdfplumber-internal failure — never surface a raw
        # traceback to a caller (the web route turns this into a friendly
        # "couldn't be read" message per Gap 2's error-reporting contract).
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

    total_redactions = sum(len(c.redactions) for c in chunks)
    needs_review = sum(1 for c in chunks if c.needs_review)
    tables = sum(1 for c in chunks if c.is_table)

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


def run_ingest(path_arg: str, doc_type: str):
    """CLI wrapper around ingest_document() — parses, redacts, and stores a
    local PDF in the education document store, printing the result."""
    result = ingest_document(Path(path_arg), doc_type)
    if not result["ok"]:
        print(result["error"])
        return 1

    print(f"Ingested {result['filename']}: {result['chunks_added']} chunks "
          f"({result['tables']} table, {result['prose']} prose)")
    print(f"Redactions applied: {result['redactions']}")
    if result["needs_review"]:
        print(f"NEEDS REVIEW: {result['needs_review']} chunk(s) flagged — "
              "human glance recommended before trusting.")
    print(f"Store: {result['store']}")
    return 0


def run_eval(golden_path: str = None, dry_run: bool = False):
    """Run golden dataset evaluation against MC pipeline."""
    import yaml

    default_path = Path(__file__).parent.parent / "tests" / "golden_education_v1.yaml"
    path = Path(golden_path) if golden_path else default_path

    if not path.exists():
        print(f"Golden dataset not found: {path}")
        print("Create one at tests/golden_education_v1.yaml or specify: mc eval <path.yaml>")
        return 1

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    queries = data.get("queries", [])
    print(f"Loaded {len(queries)} golden queries from {path.name}")

    if dry_run:
        nodes = set()
        diffs = {}
        for q in queries:
            if q.get("expected_node"):
                nodes.add(q["expected_node"])
            d = q.get("difficulty", "unknown")
            diffs[d] = diffs.get(d, 0) + 1
        print(f"\n--- Dry Run ---")
        print(f"  Queries: {len(queries)}")
        print(f"  Distinct nodes: {len(nodes)}")
        print(f"  Difficulties: {diffs}")
        return 0

    # Full run — use pipeline in eval mode
    pipeline = Pipeline()
    correct = 0
    total = 0

    for i, gq in enumerate(queries):
        qid = gq.get("id", f"Q{i}")
        query_text = gq["query"]
        expected_node = gq.get("expected_node")

        print(f"  [{i+1}/{len(queries)}] {qid}: {query_text[:50]}...", end="", flush=True)

        try:
            result = asyncio.run(pipeline.run(
                query_text,
                intent=gq.get("expected_intent"),
                eval_mode=True,
            ))
            actual_node = result.classification.riu_id
            match = actual_node == expected_node if expected_node else True
            if match:
                correct += 1
            total += 1
            status = "PASS" if match else "FAIL"
            print(f" → {status} (got {actual_node}, conf {result.classification.confidence:.2f})")
        except Exception as e:
            total += 1
            print(f" → ERR ({e})")

    pct = (100 * correct / total) if total > 0 else 0
    print(f"\nNode accuracy: {correct}/{total} ({pct:.1f}%)")

    results_dir = Path(__file__).parent.parent / "tests" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    results_path = results_dir / f"golden_results_{timestamp}.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "golden_path": str(path),
            "correct": correct,
            "total": total,
            "accuracy": (correct / total) if total > 0 else 0,
        }, f, indent=2)
    print(f"Results written to {results_path}")
    return 0


def run_health(capture=False, check_regression=False):
    from src.integrity.health_check import HealthCheck
    from src.integrity.regression import RegressionChecker

    hc = HealthCheck()
    result = hc.run()

    if capture:
        checker = RegressionChecker()
        path = checker.capture(result)
        print(f"Baseline captured: {path}")
        print(f"Health: {result.score:.0%} ({result.checks_passed}/{result.checks_total})")
        return 0

    if check_regression:
        checker = RegressionChecker()
        reg = checker.check(result)
        print(f"Regression: {'PASS' if reg.passed else 'FAIL'}")
        print(f"  {reg.summary}")
        for name, slo in reg.slo_results.items():
            status = "PASS" if slo["passed"] else "FAIL"
            print(f"  [{status}] {slo['description']}: {slo['value']} (threshold: {slo['threshold']})")
        return 0 if reg.passed else 1

    print(f"Health: {result.score:.0%} ({result.checks_passed}/{result.checks_total})")
    for section, data in result.sections.items():
        status = "PASS" if data["passed"] == data["total"] else "WARN"
        print(f"  [{status}] {section}: {data['passed']}/{data['total']}")
        for issue in data.get("issues", [])[:3]:
            print(f"        {issue}")
    return 0 if result.healthy else 1


def run_candidates():
    from ontology.proposals.candidate import CandidateStore
    store = CandidateStore()

    active = store.list_active()
    ready = store.list_ready()

    if not active and not ready:
        print("No candidate RIUs. The ontology covers all queries so far.")
        return 0

    if active:
        print(f"Active candidates ({len(active)}):")
        for c in active:
            print(f"  [{c.candidate_id}] {c.status} — {c.hit_count} hits, "
                  f"{len(c.signals)} signals, domain: {c.domain}")
            print(f"    Fallback: {c.fallback_node} ({c.fallback_confidence:.0%})")
            print(f"    Signals: {', '.join(c.signals[:5])}")

    if ready:
        print(f"\nReady for promotion ({len(ready)}):")
        for c in ready:
            print(f"  [{c.candidate_id}] {c.evaluation_notes}")

    return 0


def run_evaluate(candidate_id: str):
    from ontology.proposals.candidate import CandidateStore
    from ontology.engine import OntologyEngine

    store = CandidateStore()
    engine = OntologyEngine()

    candidate = store.evaluate(candidate_id, engine)
    if not candidate:
        print(f"Candidate {candidate_id} not found.")
        return 1

    print(f"Candidate: {candidate.candidate_id}")
    print(f"Status: {candidate.status}")
    print(f"Resolution: {candidate.resolution}")
    print(f"Notes: {candidate.evaluation_notes}")

    if candidate.resolution == "promote":
        print(f"\nThis candidate is ready for promotion.")
        print(f"Signals: {', '.join(candidate.signals)}")
        print(f"Hit count: {candidate.hit_count}")
        print(f"This is a Tier 1 change — requires human approval.")
    return 0


def _start_web_server():
    """Launch web server as daemon thread."""
    import threading
    try:
        from src.web import start_web_server
        thread = threading.Thread(target=start_web_server, args=(7896,), daemon=True)
        thread.start()
        return True
    except Exception:
        return False


def run_session(subcmd: str):
    if subcmd == "start":
        sid = start_session()
        web_ok = _start_web_server()
        print(f"Session started: {sid[:8]}...")
        if web_ok:
            print(f"  Web UI: http://localhost:7896")
        return 0
    elif subcmd == "end":
        summary = end_session()
        if summary:
            print(f"Session ended. {summary.get('query_count', 0)} queries, "
                  f"{summary.get('duration_seconds', 0)}s")
        else:
            print("No active session.")
        return 0
    elif subcmd == "status":
        status = session_status()
        if status:
            print(f"Active session: {status['session_id'][:8]}...")
            print(f"  Queries: {status.get('query_count', 0)}")
            print(f"  Started: {time.strftime('%H:%M:%S', time.localtime(status.get('started_at', 0)))}")
        else:
            print("No active session. Start one with: mc session start")
        return 0
    print(f"Unknown session command: {subcmd}")
    return 1


def run_cron(subcmd: str):
    from src.cron import CronSystem
    cron = CronSystem()

    if subcmd == "list":
        schedules = cron.list_schedules()
        if not schedules:
            print("No schedules. Add YAML files to config/schedules/")
            return 0
        for s in schedules:
            status = "ON" if s.enabled else "OFF"
            due = "DUE" if cron.is_due(s) else "waiting"
            print(f"  [{status}] {s.id}: {s.intent} every {s.interval_minutes}m ({due})")
            print(f"         {s.query[:60]}")
        return 0
    elif subcmd == "daemon":
        asyncio.run(cron.daemon())
        return 0
    elif subcmd.startswith("run"):
        schedule_id = sys.argv[3] if len(sys.argv) > 3 else None
        if not schedule_id:
            print("Usage: mc cron run <schedule-id>")
            return 1
        schedules = {s.id: s for s in cron.list_schedules()}
        if schedule_id not in schedules:
            print(f"Schedule not found: {schedule_id}")
            return 1
        result = asyncio.run(cron.run_schedule(schedules[schedule_id]))
        print(f"Ran {schedule_id}: {result['classification']} (conf: {result['confidence']:.2f})")
        return 0
    print(f"Unknown cron command: {subcmd}")
    return 1


def _self_invoke(*args: str) -> list:
    """
    Build an argv that re-runs THIS program with the given args.

    Frozen (PyInstaller .exe): sys.executable is the mc binary itself →
    [mc, *args]. Source: sys.executable is python → [python, mc_cli.py, *args].
    This is what lets `mc start` spawn the web server without a system
    python3 — the old code called ["python3", "src/api_server.py"], which
    does not exist inside the packaged binary, so the server silently never
    came up. Same fix as mission-canvas/src/mc_cli.py's _self_invoke.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__)), *args]


def run_serve(port: int = 7896):
    """
    Run the web UI server in the foreground (blocking). FastAPI + WebSocket,
    serves static/index.html at / and the /api/* + ws endpoints. Launched as
    a subprocess by run_start(); also usable directly as `mc serve`.
    """
    from src.web import start_web_server
    start_web_server(port)
    return 0


def run_start():
    import subprocess
    root = str(Path(__file__).parent.parent)
    pidfile = Path(root) / ".mc_pids"
    pids = []

    print("Starting Mission Canvas services...")

    # Web server — re-exec self (works whether frozen or from source)
    p = subprocess.Popen(
        _self_invoke("serve", "7896"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pids.append(str(p.pid))
    print(f"  Web server: PID {p.pid} on :7896")

    # Broker + Hub (if Node available)
    import shutil
    if shutil.which("node"):
        runtime = f"{root}/runtime"
        p2 = subprocess.Popen(
            ["node", f"{runtime}/broker/index.mjs"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pids.append(str(p2.pid))
        print(f"  Broker: PID {p2.pid} on :7899")

        p3 = subprocess.Popen(
            ["node", f"{runtime}/hub/server.mjs"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pids.append(str(p3.pid))
        print(f"  Hub: PID {p3.pid} on :7890")

    pidfile.write_text("\n".join(pids))
    print(f"\nServices running. Stop with: mc stop")
    return 0


def run_stop():
    import signal
    root = str(Path(__file__).parent.parent)
    pidfile = Path(root) / ".mc_pids"
    if not pidfile.exists():
        print("No running services found.")
        return 0

    pids = pidfile.read_text().strip().split("\n")
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
            print(f"  Stopped PID {pid}")
        except (ProcessLookupError, ValueError):
            pass
    pidfile.unlink()
    print("All services stopped.")
    return 0


def run_stats():
    engine = OntologyEngine()
    kl = KnowledgeStore()
    memory = MemoryStore()

    print("Mission Canvas — Compounding Metrics")
    print(f"  Ontology nodes:    {engine.node_count}")
    print(f"  Domains:           {engine.domain_count}")
    print(f"  Knowledge entries: {kl.entry_count}")
    print(f"  Citations:         {kl.citation_count}")
    print(f"  Path records:      {memory.total_path_count()}")
    print(f"  Gap signals:       {memory.gap_signal_count()}")
    print(f"  Redis connected:   {memory.redis_connected()}")
    return 0



async def run_codex(subcmd: str, args: list[str]):
    from src.codex_adapter import (
        CodexEnvelopeStore,
        load_result_file,
        summarize_results,
        task_envelope_from_pipeline_result,
    )

    store = CodexEnvelopeStore()

    if subcmd == "task":
        if len(args) < 2:
            print('Usage: mc codex task <intent> "<task description>"')
            return 1
        intent_name = args[0].lower()
        if intent_name not in INTENTS:
            print(f"Unknown intent: {intent_name}")
            print(f"Available: {', '.join(INTENTS.keys())}")
            return 1
        query = " ".join(args[1:])
        pipeline = Pipeline()
        result = await pipeline.run(query, intent=INTENTS[intent_name])
        envelope = task_envelope_from_pipeline_result(
            query=query,
            requested_intent=INTENTS[intent_name],
            result=result,
        )
        store.write_task(envelope)
        print(json.dumps(envelope, indent=2, sort_keys=True))
        return 0

    if subcmd == "result":
        if len(args) < 2:
            print("Usage: mc codex result <task_id> <json-file|->")
            return 1
        task_id, result_path = args[0], args[1]
        task = store.find_task(task_id)
        if not task:
            print(f"Task not found: {task_id}")
            return 1
        result = load_result_file(result_path)
        if result.get("task_id") and result["task_id"] != task_id:
            print(f"Result task_id mismatch: {result['task_id']} != {task_id}")
            return 1
        result["task_id"] = task_id
        result.setdefault("task", {
            "classification": task.get("classification"),
            "objective": task.get("objective"),
            "policy": task.get("policy"),
        })
        record = store.write_result(result)
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0

    if subcmd == "history":
        query = " ".join(args)
        records = store.list_results(query=query, limit=20)
        print(summarize_results(records, limit=20))
        return 0

    if subcmd == "tasks":
        for task in store.list_tasks(limit=20):
            cls = task.get("classification", {})
            print(f"{task.get('task_id')} [{cls.get('riu')}] {task.get('objective', '')[:100]}")
        return 0

    print("Usage: mc codex task|result|history|tasks ...")
    return 1


async def run_intent(intent_name: str, query: str):
    intent = INTENTS.get(intent_name)
    # Use active session if one exists
    session_id = get_active_session()
    if not intent:
        print(f"Unknown intent: {intent_name}")
        print(f"Available: {', '.join(INTENTS.keys())}")
        return 1

    retriever = _document_retriever()
    from src.education.pipeline_execute import EducationExecutor
    pipeline = Pipeline(
        document_retriever=retriever,
        education_executor=EducationExecutor(document_retriever=retriever),
    )
    result = await pipeline.run(query, intent=intent, session_id=session_id)
    if session_id:
        increment_session()

    print(f"[{result.classification.riu_id}] {result.classification.name}")
    print(f"Confidence: {result.classification.confidence:.2f} → {result.path_record.confidence_at_exit:.2f}")
    print(f"Steps: {' → '.join(result.steps_executed)}")
    print(f"External: {'Yes' if result.external_called else 'No'}")
    if result.gap_signals:
        print(f"Gaps: {', '.join(result.gap_signals)}")
    print(f"Duration: {result.duration_ms}ms")
    print()
    print(result.synthesis.content)
    if intent_name == "reflect" and "codex" in query.lower():
        from src.codex_adapter import CodexEnvelopeStore, summarize_results
        records = CodexEnvelopeStore().list_results(query="codex", limit=10)
        print()
        print("--- Codex Execution History ---")
        print(summarize_results(records, limit=10))
    return 0


def run_onboard(args: list[str]) -> int:
    """Handle integration onboarding interview commands."""
    from src.integration_onboarding import (
        IntegrationOnboarding,
        PHASE_PATTERN,
        PHASE_SCOPE,
        PHASE_GOVERNANCE,
        PHASE_ASSEMBLY,
        PHASE_VERIFY,
        PHASE_DONE,
        PHASE_NAMES,
    )

    if not args:
        print("\nUsage:")
        print("  mc onboard start \"<purpose_text>\"")
        print("  mc onboard status")
        print("  mc onboard decide <BRIDGE|CAPTURE> \"<reasoning>\"")
        print("  mc onboard scope <platform> <channels_csv_or_-> <destination>")
        print("  mc onboard governance <CONSERVATIVE|WIDEN> \"<rationale>\"")
        print("  mc onboard assemble")
        print("  mc onboard verify <pass|fail> \"<smoke_query>\" [\"<notes>\"]")
        print("  mc onboard list")
        print("  mc onboard load <onboarding_id>\n")
        return 1

    subcmd = args[0].lower()

    def get_current_id():
        path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "scratch", "onboarding", ".current_onboarding")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        ids = IntegrationOnboarding.list_all()
        if ids:
            return ids[-1]
        return None

    def set_current_id(oid):
        path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "scratch", "onboarding", ".current_onboarding")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(oid)

    def print_options(options):
        for opt in options:
            star = " (recommended)" if opt.get("recommended") else ""
            print(f"     [{opt['id']}]{star} {opt['description']}")
            print(f"         Offers: {opt['offers']}\n")

    if subcmd == "list":
        ids = IntegrationOnboarding.list_all()
        current = get_current_id()
        print("\nActive Onboarding Interviews:")
        for oid in ids:
            star = "*" if oid == current else " "
            print(f"  {star} {oid}")
        print()
        return 0

    if subcmd == "start":
        if len(args) < 2:
            print("Usage: mc onboard start \"<purpose_text>\"")
            return 1
        purpose_text = args[1]

        onboarding = IntegrationOnboarding()
        oid = onboarding.start(purpose_text)
        set_current_id(oid)
        print(f"\n✓ Started onboarding interview: {oid}")
        print("  Purpose captured. Progressed to Pattern Selection phase.\n")

        decision = onboarding.get_pattern_decision()
        print(f"👉 {decision['signal_note']}\n")
        print("   Options:")
        print_options(decision["options"])
        print("   To decide, run:")
        print("     mc onboard decide <option_id> \"<your reasoning>\"\n")
        return 0

    oid = get_current_id()
    if not oid:
        print("\n✗ No active onboarding interview. Start one with: mc onboard start \"<purpose>\"\n")
        return 1

    onboarding = IntegrationOnboarding()
    if not onboarding.load(oid):
        print(f"\n✗ Failed to load onboarding interview {oid}\n")
        return 1

    if subcmd == "load":
        if len(args) < 2:
            print("Usage: mc onboard load <onboarding_id>")
            return 1
        target_oid = args[1]
        if target_oid in IntegrationOnboarding.list_all():
            set_current_id(target_oid)
            print(f"\n✓ Active onboarding interview set to: {target_oid}\n")
            return 0
        else:
            print(f"\n✗ Onboarding interview {target_oid} not found.\n")
            return 1

    elif subcmd == "status":
        print("\n==========================================")
        print(f"Onboarding ID: {onboarding.onboarding_id}")
        phase = onboarding.state["current_phase"]
        print(f"Current Phase: {PHASE_NAMES.get(phase, 'Unknown')}")
        print("==========================================\n")

        if phase == PHASE_PATTERN:
            decision = onboarding.get_pattern_decision()
            print(f"👉 {decision['signal_note']}\n")
            print("   Options:")
            print_options(decision["options"])
            print("   To decide, run:")
            print("     mc onboard decide <option_id> \"<your reasoning>\"\n")
        elif phase == PHASE_SCOPE:
            print("Current status: Scope.")
            print("Run 'mc onboard scope <platform> <channels_csv_or_-> <destination>' to proceed.\n")
        elif phase == PHASE_GOVERNANCE:
            decision = onboarding.get_governance_decision()
            print("👉 Governance options:")
            print_options(decision["options"])
            print("   To decide, run:")
            print("     mc onboard governance <option_id> \"<rationale>\"\n")
        elif phase == PHASE_ASSEMBLY:
            print("Current status: Assembly.")
            print("Run 'mc onboard assemble' to generate integration_config + bridge_wiring_record.\n")
        elif phase == PHASE_VERIFY:
            print("Current status: Verify.")
            print("Run 'mc onboard verify <pass|fail> \"<smoke_query>\"' after testing the wired bot.\n")
        elif phase == PHASE_DONE:
            print("Current status: Complete. Artifacts generated:")
            print(f"  Config: {onboarding.state['artifacts']['integration_config']}")
            print(f"  Wiring Record: {onboarding.state['artifacts']['bridge_wiring_record']}\n")
        return 0

    elif subcmd == "decide":
        if len(args) < 3:
            print("Usage: mc onboard decide <option_id> \"<reasoning>\"")
            return 1
        option_id = args[1]
        reasoning = " ".join(args[2:])
        ok, msg = onboarding.decide_pattern(option_id, reasoning)
        if ok:
            print(f"\n✓ {msg}\n")
            print("👉 Next: run 'mc onboard scope <platform> <channels_csv_or_-> <destination>'\n")
            return 0
        else:
            print(f"\n✗ {msg}\n")
            return 1

    elif subcmd == "scope":
        if len(args) < 4:
            print("Usage: mc onboard scope <platform> <channels_csv_or_-> <destination>")
            return 1
        platform = args[1]
        channels_raw = args[2]
        channels = [] if channels_raw == "-" else [c.strip() for c in channels_raw.split(",") if c.strip()]
        destination = args[3]
        ok, msg = onboarding.set_scope(platform, channels, destination)
        if ok:
            print(f"\n✓ {msg}\n")
            decision = onboarding.get_governance_decision()
            print("👉 Governance options:")
            print_options(decision["options"])
            print("   To decide, run:")
            print("     mc onboard governance <option_id> \"<rationale>\"\n")
            return 0
        else:
            print(f"\n✗ {msg}\n")
            return 1

    elif subcmd == "governance":
        if len(args) < 3:
            print("Usage: mc onboard governance <CONSERVATIVE|WIDEN> \"<rationale>\"")
            return 1
        option_id = args[1]
        rationale = " ".join(args[2:])
        ok, msg = onboarding.decide_governance(option_id, rationale)
        if ok:
            print(f"\n✓ {msg}\n")
            print("👉 Next: run 'mc onboard assemble'\n")
            return 0
        else:
            print(f"\n✗ {msg}\n")
            return 1

    elif subcmd == "assemble":
        ok, msg = onboarding.run_assembly()
        if ok:
            print(f"\n✓ {msg}")
            print(f"  Config: {onboarding.state['artifacts']['integration_config']}")
            print(f"  Wiring Record: {onboarding.state['artifacts']['bridge_wiring_record']}\n")
            print("👉 Next: run 'mc onboard verify <pass|fail> \"<smoke_query>\" [\"<notes>\"]' after testing the wired bot.\n")
            return 0
        else:
            print(f"\n✗ {msg}\n")
            return 1

    elif subcmd == "verify":
        if len(args) < 3:
            print("Usage: mc onboard verify <pass|fail> \"<smoke_query>\" [\"<notes>\"]")
            return 1
        result = args[1]
        smoke_query = args[2]
        notes = " ".join(args[3:]) if len(args) > 3 else ""
        ok, msg = onboarding.run_verify(smoke_query, result, notes)
        if ok:
            print(f"\n✓ {msg}\n")
            return 0
        else:
            print(f"\n✗ {msg}\n")
            return 1

    else:
        print(f"\nUnknown onboard subcommand: {subcmd}\n")
        return 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    cmd = sys.argv[1].lower()

    if cmd == "eval":
        dry_run = "--dry-run" in sys.argv
        golden_path = None
        for arg in sys.argv[2:]:
            if not arg.startswith("--") and arg.endswith(".yaml"):
                golden_path = arg
        return run_eval(golden_path=golden_path, dry_run=dry_run)
    elif cmd == "health":
        capture = "--capture" in sys.argv
        regression = "--check-regression" in sys.argv
        return run_health(capture=capture, check_regression=regression)
    elif cmd == "stats":
        return run_stats()
    elif cmd == "candidates":
        return run_candidates()
    elif cmd == "evaluate":
        if len(sys.argv) < 3:
            print("Usage: mc evaluate <candidate-id>")
            return 1
        return run_evaluate(sys.argv[2])
    elif cmd == "session":
        return run_session(sys.argv[2] if len(sys.argv) > 2 else "status")
    elif cmd == "cron":
        return run_cron(sys.argv[2] if len(sys.argv) > 2 else "list")
    elif cmd == "codex":
        if len(sys.argv) < 3:
            print("Usage: mc codex task|result|history|tasks ...")
            return 1
        return asyncio.run(run_codex(sys.argv[2].lower(), sys.argv[3:]))
    elif cmd == "ingest":
        if len(sys.argv) < 3:
            print("Usage: mc ingest <path.pdf> --type=curriculum|organizational")
            return 1
        doc_type = "curriculum"
        for arg in sys.argv[3:]:
            if arg.startswith("--type="):
                doc_type = arg.split("=", 1)[1]
        return run_ingest(sys.argv[2], doc_type)
    elif cmd == "serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 7896
        return run_serve(port)
    elif cmd == "start":
        return run_start()
    elif cmd == "stop":
        return run_stop()
    elif cmd == "onboard":
        return run_onboard(sys.argv[2:])
    elif cmd == "open":
        import subprocess
        import platform
        url = "http://127.0.0.1:7896"
        if platform.system() == "Darwin":
            subprocess.Popen(["open", url], stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", url], stderr=subprocess.DEVNULL)
        return 0
    elif cmd in INTENTS:
        if len(sys.argv) < 3:
            print(f"Usage: mc {cmd} \"<query>\"")
            return 1
        query = " ".join(sys.argv[2:])
        return asyncio.run(run_intent(cmd, query))
    else:
        # Treat the entire input as a query, auto-classify
        query = " ".join(sys.argv[1:])
        return asyncio.run(run_intent("research", query))


if __name__ == "__main__":
    sys.exit(main() or 0)
