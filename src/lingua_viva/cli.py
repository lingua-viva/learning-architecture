from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from doctor.support_loop.doctor import format_teacher_summary, run_doctor

from .config import provider_status
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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
