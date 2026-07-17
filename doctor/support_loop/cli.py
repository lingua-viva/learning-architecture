from __future__ import annotations

import argparse
import json

from .doctor import format_teacher_summary, run_doctor


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lv", description="Lingua Viva local support loop")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        result = run_doctor()
        _print_json(result) if args.json else print(format_teacher_summary(result))
        return 0 if result["status"] in ("OK", "WARN", "FIXABLE", "PRIVATE_RISK") else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
