from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

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
    status = provider_status()
    if args.json:
        _print_json(status)
    else:
        local = "reachable" if status["ollama_reachable"] else "not reachable"
        print(f"Lingua Viva health: local model service {local}; provider={status['provider']}")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    result = run_doctor()
    if args.json:
        _print_json(result)
    else:
        print(format_teacher_summary(result))
    return 0 if result["status"] in ("OK", "WARN", "FIXABLE", "PRIVATE_RISK") else 1


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

    doctor = sub.add_parser("doctor", help="Run the Lingua Viva Doctor")
    doctor.add_argument("--json", action="store_true")

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
    if args.command == "filemap":
        return _filemap(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
