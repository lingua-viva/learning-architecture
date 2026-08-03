from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message="jsonschema.RefResolver is deprecated.*",
)
from jsonschema import Draft202012Validator, RefResolver


SCHEMA_DIR = Path(__file__).with_name("schemas")
SCHEMA_BY_VERSION = {
    "docpipe.source.v1": "source.schema.json",
    "docpipe.extraction.v1": "extraction.schema.json",
    "docpipe.lens.v1": "lens.schema.json",
    "docpipe.observation.v1": "observation.schema.json",
    "docpipe.v1": "manifest.schema.json",
}


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _schema_store() -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for schema_path in SCHEMA_DIR.glob("*.schema.json"):
        schema = _load_json(schema_path)
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            store[schema_id] = schema
            store[schema_path.name] = schema
            store[f"https://lingua-viva.local/docpipe/{schema_path.name}"] = schema
    return store


def validate_file(path: Path) -> list[str]:
    data = _load_json(path)
    if not isinstance(data, dict):
        return ["top-level JSON value must be an object"]
    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str):
        return ["missing string schema_version"]
    schema_name = SCHEMA_BY_VERSION.get(schema_version)
    if schema_name is None:
        return [f"unsupported schema_version {schema_version!r}"]
    store = _schema_store()
    schema = store[schema_name]
    resolver = RefResolver.from_schema(schema, store=store)
    validator = Draft202012Validator(schema, resolver=resolver)
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.path))
    messages = []
    for error in errors:
        location = "$"
        if error.path:
            location += "." + ".".join(str(part) for part in error.path)
        messages.append(f"{location}: {error.message}")
    messages.extend(_semantic_errors(data))
    return messages


def _semantic_errors(data: dict[str, Any]) -> list[str]:
    if data.get("schema_version") != "docpipe.extraction.v1":
        return []
    normalized_text = data.get("normalized_text")
    spans = data.get("spans")
    if not isinstance(normalized_text, str) or not isinstance(spans, list):
        return []
    errors: list[str] = []
    seen: set[str] = set()
    for index, span in enumerate(spans):
        if not isinstance(span, dict):
            continue
        span_id = span.get("span_id")
        if isinstance(span_id, str):
            if span_id in seen:
                errors.append(f"$.spans.{index}.span_id: duplicate span_id {span_id!r}")
            seen.add(span_id)
        start = span.get("char_start")
        end = span.get("char_end")
        text = span.get("text")
        if not isinstance(start, int) or not isinstance(end, int) or not isinstance(text, str):
            continue
        if not 0 <= start < end <= len(normalized_text):
            errors.append(
                f"$.spans.{index}: char offsets {start}:{end} are outside normalized_text"
            )
            continue
        expected = normalized_text[start:end]
        if text != expected:
            errors.append(
                f"$.spans.{index}.text: does not match normalized_text[{start}:{end}]"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Lingua Viva docpipe vault JSON file."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        errors = validate_file(args.path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{args.path}: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"{args.path}: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
