from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import yaml

from doctor.support_loop.doctor import format_teacher_summary, run_doctor

from .config import provider_status
from .filemap import add_exclusion, clear_map, load_map, run_scan, to_api
from .privacy import is_private_path
from .reasoning import ReasoningEngine


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


async def _chat_once(args: argparse.Namespace) -> int:
    engine = ReasoningEngine()
    result = await engine.reason(
        args.prompt,
        context={"riu_id": "lingua-viva-cli"},
        model=args.model,
        system_prompt=args.system_prompt or "You are Lingua Viva, a local-first teacher support tool.",
    )
    if args.json:
        _print_json(result.__dict__)
    else:
        print(result.content)
    return 0


def _ingest(args: argparse.Namespace) -> int:
    path = Path(args.pdf)
    if is_private_path(path):
        print("Refused: this path matches a private Lingua Viva data rule.")
        return 2
    if path.suffix.lower() != ".pdf":
        print("Refused: ingest currently accepts PDF files only.")
        return 2
    if not path.exists():
        print(f"Refused: file not found: {path}")
        return 2
    print(f"Ready to ingest PDF: {path}")
    return 0


def _health(args: argparse.Namespace) -> int:
    if getattr(args, "full", False):
        return _full_health(args)
    status = provider_status()
    if args.json:
        import shutil

        status["voice"] = {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "faster_whisper_installed": _faster_whisper_installed(),
            "local_stt": bool(shutil.which("ffmpeg") and _faster_whisper_installed()),
        }
        _print_json(status)
    else:
        local = "reachable" if status["ollama_reachable"] else "not reachable"
        print(f"Lingua Viva health: local model service {local}; provider={status['provider']}")
        voice = "available" if _faster_whisper_installed() else "not installed"
        print(f"Voice STT: {voice}")
    return 0


def _faster_whisper_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def _doctor(args: argparse.Namespace) -> int:
    result = run_doctor()
    if args.json:
        _print_json(result)
    else:
        print(format_teacher_summary(result))
    return 0 if result["status"] in ("OK", "WARN", "FIXABLE", "PRIVATE_RISK") else 1


def _serve(args: argparse.Namespace) -> int:
    from src.web import start_web_server

    start_web_server(args.port)
    return 0


def _eval(args: argparse.Namespace) -> int:
    if args.eval_command != "golden":
        return 1
    from ontology.engine import OntologyEngine

    path = Path(args.path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    queries = data.get("queries", [])
    engine = OntologyEngine()
    passed = 0
    failed = []
    for item in queries:
        query = str(item.get("query") or "")
        expected_node = item.get("expected_node")
        expected_intent = item.get("expected_intent")
        result = engine.classify(query, expected_intent)
        ok = result.riu_id == expected_node
        if ok:
            passed += 1
        else:
            failed.append({
                "id": item.get("id"),
                "expected": expected_node,
                "actual": result.riu_id,
                "domain": result.domain,
            })
    summary = {"total": len(queries), "passed": passed, "failed": len(failed), "failures": failed[:20]}
    if getattr(args, "quiet", False):
        pass
    elif args.json:
        _print_json(summary)
    else:
        print(f"Golden eval: {passed}/{len(queries)} passed")
        for failure in failed[:20]:
            print(f"- {failure['id']}: expected {failure['expected']}, got {failure['actual']}")
    return 0 if not failed else 1


def _full_health(args: argparse.Namespace) -> int:
    doctor = run_doctor(write_log=False)
    pytest_run = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        text=True,
        capture_output=True,
    )
    gauntlet = subprocess.run(
        [sys.executable, "doctor/lv_artifact_gauntlet.py"],
        text=True,
        capture_output=True,
    )
    eval_status = _eval(argparse.Namespace(eval_command="golden", path="tests/golden_education_v1.yaml", json=False, quiet=True))

    from .request_log import count_5xx
    server_5xx = count_5xx()

    result = {
        "doctor": doctor.get("status"),
        "pytest": "PASS" if pytest_run.returncode == 0 else "FAIL",
        "pytest_summary": (pytest_run.stdout.strip().splitlines() or [""])[-1],
        "gauntlet": "PASS" if gauntlet.returncode == 0 else "FAIL",
        "golden_eval": "PASS" if eval_status == 0 else "FAIL",
        "server_5xx": "PASS" if server_5xx == 0 else f"FAIL ({server_5xx} 5xx responses logged)",
    }
    if args.json:
        _print_json(result)
    else:
        print(f"Doctor: {result['doctor']}")
        print(f"Pytest: {result['pytest']} — {result['pytest_summary']}")
        print(f"Gauntlet: {result['gauntlet']}")
        print(f"Golden eval: {result['golden_eval']}")
        print(f"Server 5xx: {result['server_5xx']}")
    return 0 if (
        doctor.get("status") in {"OK", "WARN", "FIXABLE"}
        and pytest_run.returncode == 0
        and gauntlet.returncode == 0
        and eval_status == 0
        and server_5xx == 0
    ) else 1


def _preflight(args: argparse.Namespace) -> int:
    """Fast structural checks (<5 seconds), run before every commit.

    Complements `lv health --full` (comprehensive, slower): preflight
    catches structural breaks — UI contract drift, broken imports,
    unparseable golden file, ontology/MANIFEST count mismatch, staged
    conflict markers — in seconds. Cloned from Mission Canvas's own
    `mc preflight` (src/mc_cli.py::cmd_preflight), which caught a real
    contract violation on its first run.
    """
    import time

    start = time.time()
    root = Path(__file__).resolve().parent.parent.parent
    checks: list[tuple] = []

    # 1. UI bundle contract valid (§3)
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_ui_contract.py")],
        capture_output=True, text=True, cwd=root,
    )
    if result.returncode == 0:
        checks.append(("ui_contract", True))
    else:
        lines = (result.stdout or result.stderr).strip().splitlines()
        checks.append(("ui_contract", False, lines[0] if lines else "check failed"))

    # 2. Golden file exists and parses
    golden = root / "tests" / "golden_education_v1.yaml"
    if golden.is_file():
        try:
            with open(golden, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            n_queries = len(data.get("queries", []))
            if n_queries > 0:
                checks.append(("golden_parses", True, f"{n_queries} queries"))
            else:
                checks.append(("golden_parses", False, "0 queries"))
        except Exception as e:
            checks.append(("golden_parses", False, str(e)))
    else:
        checks.append(("golden_parses", False, "tests/golden_education_v1.yaml missing"))

    # 3. Key imports succeed
    try:
        from src.web import app  # noqa: F401
        from src.lingua_viva.reasoning import ReasoningEngine as _RE  # noqa: F401
        from src.lingua_viva.privacy import is_private_path as _ipp  # noqa: F401
        from src.lingua_viva.filemap import load_map as _lm  # noqa: F401
        checks.append(("imports", True))
    except Exception as e:
        checks.append(("imports", False, str(e)))

    # 4. Ontology loads — node count must match MANIFEST (makes doc/count
    # drift a failing check instead of accumulating silently, §6).
    try:
        from ontology.engine import OntologyEngine
        engine = OntologyEngine()
        manifest = yaml.safe_load((root / "MANIFEST.yaml").read_text(encoding="utf-8")) or {}
        expected = manifest.get("ontology", {}).get("nodes")
        if expected is not None and engine.node_count != expected:
            checks.append((
                "ontology", False,
                f"{engine.node_count} nodes loaded but MANIFEST.yaml declares {expected}",
            ))
        else:
            checks.append(("ontology", True, f"{engine.node_count} nodes"))
    except Exception as e:
        checks.append(("ontology", False, str(e)))

    # 5. No conflict markers in staged files. Anchored regex (-G) matches
    # real merge markers ("<{7} branch") without false-positives on files
    # that merely mention the marker string in prose or code (this
    # preflight's own source, for example).
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=root,
    )
    if staged.returncode == 0 and staged.stdout.strip():
        conflict = subprocess.run(
            ["git", "diff", "--cached", "-G", "^<{7} ", "--name-only"],
            capture_output=True, text=True, cwd=root,
        )
        offenders = conflict.stdout.strip()
        if conflict.returncode == 0 and offenders:
            checks.append(("no_conflicts", False, offenders.replace("\n", ", ")))
        else:
            checks.append(("no_conflicts", True))
    else:
        checks.append(("no_conflicts", True))

    # 6. Every backend route is either UI-reachable (proven via a live
    # call-site literal) or explicitly classified backend-only, with a
    # reason (dev/ROOT_CAUSE_BUILT_NOT_MOUNTED_2026-07-23.md §5). Catches
    # new routes landing with no UI trigger before they ship silently.
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_route_reachability.py")],
        capture_output=True, text=True, cwd=root,
    )
    if result.returncode == 0:
        checks.append(("route_reachability", True))
    else:
        lines = (result.stdout or result.stderr).strip().splitlines()
        checks.append(("route_reachability", False, lines[0] if lines else "check failed"))

    elapsed = time.time() - start
    passed = sum(1 for c in checks if c[1])
    failed = sum(1 for c in checks if not c[1])

    if getattr(args, "json", False):
        _print_json({
            "checks": [
                {"name": c[0], "passed": c[1], "detail": c[2] if len(c) > 2 else None}
                for c in checks
            ],
            "passed": passed,
            "total": passed + failed,
            "elapsed_seconds": round(elapsed, 2),
        })
    else:
        for check in checks:
            status = "\u2713" if check[1] else "\u2717"
            detail = f" ({check[2]})" if len(check) > 2 else ""
            print(f"  {status} {check[0]}{detail}")
        print(f"\nPreflight: {passed}/{passed + failed} in {elapsed:.1f}s")

    return 0 if failed == 0 else 1


def _filemap(args: argparse.Namespace) -> int:
    if args.filemap_command == "show":
        _print_json(to_api(load_map()))
        return 0
    if args.filemap_command == "scan":
        mapped = run_scan(args.path, max_depth=args.max_depth)
        summary = to_api(mapped)["summary"]
        print(f"Scanned {summary['total_directories']} directories; student zones excluded: {summary['student_zones_excluded']}")
        return 0
    if args.filemap_command == "exclude":
        add_exclusion(args.path)
        print(f"Excluded {args.path}")
        return 0
    if args.filemap_command == "clear":
        clear_map()
        print("Cleared file map")
        return 0
    return 1


def _audit(args) -> int:
    """Lagging-indicator audit over gap_signals.ndjson (read-only).

    SPEC_LV_GAP_SIGNAL_AUDIT_2026-07-26.md — ported from Mission Canvas's
    `mc improve --audit`: exit 1 only on NEW drift once a baseline exists
    (write one with --journal-write); --strict restores absolute semantics.
    """
    from .gap_audit import run_audit

    return run_audit(
        last=args.last,
        journal_write=args.journal_write,
        strict=args.strict,
        json_out=args.json,
    )


def _distill(args) -> int:
    """Distill LV's measurement stores into a ranked, reconciled view
    (SPEC_LV_MEASUREMENT_DISTILLATION_2026-07-26). Sibling of `lv audit`
    (drift gate, exit codes) — `lv distill` is the operator-facing ranked
    report: breadth-ranked gap clusters, candidate retirement + engine
    replay, revision-log concentration and proxy->live transitions.
    Read-only by default; `--write-summary` opts into one longitudinal
    record. Not in preflight (engine replay exceeds the <5s budget).
    """
    from src.lingua_viva.improvement_audit import (
        append_summary_record,
        build_audit_report,
        compute_delta,
        format_report,
        previous_summary,
        summary_record,
    )

    classify_fn = None
    if not getattr(args, "no_replay", False):
        from ontology.engine import OntologyEngine

        engine = OntologyEngine()

        def classify_fn(query: str) -> tuple[str, float]:
            result = engine.classify(query)
            return result.riu_id, result.confidence

    report = build_audit_report(classify_fn=classify_fn)
    prev = previous_summary()

    if args.json:
        payload = dict(report)
        payload["summary"] = summary_record(report)
        _print_json(payload)
    else:
        print(format_report(report))
        if prev:
            print("")
            print("[6] DELTA vs previous distill run")
            for line in compute_delta(prev, summary_record(report)) or ["no change"]:
                print(f"  {line}")

    if getattr(args, "write_summary", False):
        record = append_summary_record(report)
        if not args.json:
            print(f"\nSummary record appended ({record['generated_at']}).")
    return 0


def _candidates(args) -> int:
    """Read-only listing of candidate ontology nodes (Track A item 3,
    REPORT_LV_EXTERNAL_FEEDBACK_TRANSFER_2026-07-25.md).

    The system proposes, the human disposes — this command is the "human sees"
    half. It never evaluates, promotes, or discards; candidate YAML files under
    ontology/proposals/ remain untouched.
    """
    from ontology.proposals.candidate import CandidateStore

    store = CandidateStore()
    rows = []
    for path in sorted(store._dir.glob("CAND-*.yaml")):
        candidate = store.get(path.stem)
        if candidate is None:
            continue
        resolved = candidate.status in ("PROMOTED", "DISCARDED") or (
            candidate.resolution or ""
        ).startswith("discarded")
        if resolved and not args.all:
            continue
        rows.append(candidate)

    if not rows:
        scope = "candidates" if args.all else "active candidates"
        print(f"No {scope} — the ontology has no open classification gaps on record.")
        return 0

    print(f"{'ID':<14} {'STATUS':<10} {'HITS':>4} {'DOMAIN':<12} SIGNALS")
    for c in rows:
        signals = ", ".join(c.signals[:4]) + ("…" if len(c.signals) > 4 else "")
        print(f"{c.candidate_id:<14} {c.status:<10} {c.hit_count:>4} {c.domain:<12} {signals}")
        if c.resolution:
            print(f"{'':<14} resolution: {c.resolution}")
    print(f"\n{len(rows)} candidate(s). Files: {store._dir}/CAND-*.yaml (read-only view)")
    return 0


def _spec_status(args: argparse.Namespace) -> int:
    from .spec_status import _main as spec_status_main

    argv: list[str] = []
    if args.json:
        argv.append("--json")
    if args.markdown:
        argv.append("--markdown")
    if args.strict:
        argv.append("--strict")
    return spec_status_main(argv)


def _golden_workflows(args: argparse.Namespace) -> int:
    from src.lingua_viva.golden_workflows.runner import print_matrix, run_workflows

    mode = "live" if args.live else "hermetic"
    results = run_workflows(mode=mode, only=args.only)
    payload = {"results": [r.as_dict() for r in results], "passed": sum(1 for r in results if r.status == "PASS"), "total": len(results)}
    if args.json:
        _print_json(payload)
    else:
        print(print_matrix(results))
    return 0 if all(r.status in {"PASS", "SKIPPED_MISSING_CREDENTIALS"} for r in results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lv", description="Lingua Viva local runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Ask the local Lingua Viva reasoning engine")
    chat.add_argument("prompt")
    chat.add_argument("--model")
    chat.add_argument("--system-prompt")
    chat.add_argument("--json", action="store_true")

    ingest = sub.add_parser("ingest", help="Validate a PDF path for local ingestion")
    ingest.add_argument("pdf")

    health = sub.add_parser("health", help="Show local model/provider health")
    health.add_argument("--json", action="store_true")
    health.add_argument("--full", action="store_true", help="Run Doctor, tests, gauntlet, and golden eval")

    doctor = sub.add_parser("doctor", help="Run the Lingua Viva Doctor")
    doctor.add_argument("--json", action="store_true")

    preflight = sub.add_parser("preflight", help="Fast structural checks (<5s), run before every commit")
    preflight.add_argument("--json", action="store_true")

    serve = sub.add_parser("serve", help="Start the local Lingua Viva web app")
    serve.add_argument("port", nargs="?", type=int, default=8787)

    eval_parser = sub.add_parser("eval", help="Run Lingua Viva evaluation suites")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    golden = eval_sub.add_parser("golden", help="Run the education golden classification suite")
    golden.add_argument("path", nargs="?", default="tests/golden_education_v1.yaml")
    golden.add_argument("--json", action="store_true")

    audit = sub.add_parser(
        "audit",
        help="Lagging-indicator audit over gap signals (exit 1 on new drift)",
    )
    audit.add_argument("--last", type=int, default=None, metavar="N",
                       help="Audit only the last N journal records")
    audit.add_argument("--journal-write", action="store_true",
                       help="Append a summary record (full runs become the delta baseline)")
    audit.add_argument("--strict", action="store_true",
                       help="Absolute exit semantics: any WARN exits 1, baseline ignored")
    audit.add_argument("--json", action="store_true")

    distill = sub.add_parser(
        "distill",
        help="Ranked distillation of gap clusters, candidates, and revision log (read-only)",
    )
    distill.add_argument("--json", action="store_true")
    distill.add_argument("--no-replay", action="store_true",
                         help="Skip replaying candidate queries through the engine (faster)")
    distill.add_argument("--write-summary", action="store_true",
                         help="Append one longitudinal summary record for future run-over-run deltas")

    candidates = sub.add_parser(
        "candidates",
        help="List candidate ontology nodes proposed from classification gaps (read-only)",
    )
    candidates.add_argument(
        "--all",
        action="store_true",
        help="Include resolved candidates (promoted/discarded), not just active ones",
    )

    spec_status = sub.add_parser("spec-status", help="Report spec/status drift")
    spec_status.add_argument("--json", action="store_true", help="Print JSON report")
    spec_status.add_argument("--markdown", action="store_true", help="Print Markdown report")
    spec_status.add_argument("--strict", action="store_true", help="Exit 1 when warn or fail findings exist")

    golden_workflows = sub.add_parser("golden-workflows", help="Run integration-loop golden workflows")
    mode = golden_workflows.add_mutually_exclusive_group()
    mode.add_argument("--hermetic", action="store_true", default=True)
    mode.add_argument("--live", action="store_true")
    golden_workflows.add_argument("--only", default=None)
    golden_workflows.add_argument("--json", action="store_true")

    fmap = sub.add_parser("filemap", help="Manage the local curriculum file map")
    fmap_sub = fmap.add_subparsers(dest="filemap_command", required=True)
    fmap_sub.add_parser("show", help="Show the current file map")
    scan = fmap_sub.add_parser("scan", help="Scan a directory into the file map")
    scan.add_argument("path")
    scan.add_argument("--max-depth", type=int, default=3)
    exclude = fmap_sub.add_parser("exclude", help="Add a directory exclusion")
    exclude.add_argument("path")
    fmap_sub.add_parser("clear", help="Clear the file map")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "chat":
        return asyncio.run(_chat_once(args))
    if args.command == "ingest":
        return _ingest(args)
    if args.command == "health":
        return _health(args)
    if args.command == "doctor":
        return _doctor(args)
    if args.command == "preflight":
        return _preflight(args)
    if args.command == "serve":
        return _serve(args)
    if args.command == "eval":
        return _eval(args)
    if args.command == "audit":
        return _audit(args)
    if args.command == "distill":
        return _distill(args)
    if args.command == "candidates":
        return _candidates(args)
    if args.command == "spec-status":
        return _spec_status(args)
    if args.command == "golden-workflows":
        return _golden_workflows(args)
    if args.command == "filemap":
        return _filemap(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
