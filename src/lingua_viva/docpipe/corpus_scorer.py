"""Detection-corpus scorer — Phase 0B of SPEC_LV_UNIFIED_REAL_DATA_FIX_2026-08-19.

The measurement instrument for the real-data fix wave. Scores the student
detection pipeline against a hand-labelled corpus and reports, PER FILE,
precision, recall, and false-positive count — never "students detected"
alone (a single number that goes up when you detect more is the metric that
produced 637 false positives).

Two corpora use this same scorer:
- the REAL corpus (real names, lives outside the repo, NEVER committed) —
  run locally: ``python3 -m src.lingua_viva.docpipe.corpus_scorer <dir>``
- the SYNTHETIC mirror (``tests/fixtures/docpipe/synthetic-corpus/``,
  synthetic names, committed) — run by CI via the corpus tests.

Labels format (labels.json in the corpus dir)::

    {"files": [{"file": "...", "shape": "...", "expected_students": [...],
                "sealed": false, ...}, ...]}

``sealed: true`` marks the holdout (spec §2B.3): the scorer SKIPS it unless
``--open-holdout`` is passed — it is opened exactly once, at the end (§6).

Privacy: by default the report prints COUNTS only. ``--show-names`` prints
false-positive/false-negative names and exists for local runs against the
synthetic corpus or inside the private channel — never paste real names
into shared docs.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _normalize_name(name: str) -> str:
    """Whitespace-collapsed, casefolded comparison key. Ground truth is the
    name as it appears in the file; this only forgives spacing/case noise,
    never spelling differences (those are identity resolution's job, STEP 5)."""
    return re.sub(r"\s+", " ", str(name or "")).strip().casefold()


def _build_source(path: Path, content: bytes):
    from src.lingua_viva.docpipe.contracts import SourceRecord

    ext = path.suffix.lower()
    mime = mimetypes.guess_type(path.name)[0] or (
        "text/markdown" if ext in (".md", ".markdown") else "application/octet-stream"
    )
    return SourceRecord({
        "schema_version": "docpipe.source.v1",
        "source_id": f"SRC-{uuid.uuid4()}",
        "origin": "local",
        "drive_file_id": None,
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "imported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mime": mime,
        "owner": "teacher:corpus-scorer",
        "original_filename": path.name,
        "original_ext": ext,
        "byte_size": len(content),
    })


def detect_names(path: Path) -> list[str]:
    """Run the REAL extraction pipeline (deterministic core, no model — the
    scorer must never depend on which model happens to be resident) and
    return the detected student display names."""
    from src.lingua_viva.docpipe import extract as docpipe_extract

    content = path.read_bytes()
    source = _build_source(path, content)
    extraction = asyncio.run(
        docpipe_extract.extract_document(source, content, model_client=None)
    )
    return [
        str(student.get("display_name") or "").strip()
        for student in extraction.data.get("structure", {}).get("students_detected", [])
        if isinstance(student, dict) and str(student.get("display_name") or "").strip()
    ]


def score_names(expected: list[str], detected: list[str]) -> dict:
    """Pure scoring math — set comparison on normalized names."""
    expected_keys = {_normalize_name(n): n for n in expected if str(n).strip()}
    detected_keys = {_normalize_name(n): n for n in detected if str(n).strip()}
    tp = sorted(k for k in detected_keys if k in expected_keys)
    fp = sorted(k for k in detected_keys if k not in expected_keys)
    fn = sorted(k for k in expected_keys if k not in detected_keys)
    precision = len(tp) / len(detected_keys) if detected_keys else None
    recall = len(tp) / len(expected_keys) if expected_keys else None
    return {
        "expected_count": len(expected_keys),
        "detected_count": len(detected_keys),
        "true_positives": len(tp),
        "false_positives": len(fp),
        "false_negatives": len(fn),
        "precision": precision,
        "recall": recall,
        "false_positive_names": [detected_keys[k] for k in fp],
        "false_negative_names": [expected_keys[k] for k in fn],
    }


def score_corpus(corpus_dir: Path, *, open_holdout: bool = False,
                 labels_name: str = "labels.json") -> list[dict]:
    """Score every labelled file in the corpus. Sealed files are reported as
    sealed (and NOT scored) unless open_holdout is set."""
    corpus_dir = Path(corpus_dir)
    labels_path = corpus_dir / labels_name
    if not labels_path.exists():
        # real-corpus layout keeps labels in a corpus/ subdir next to the files
        alt = corpus_dir / "corpus" / labels_name
        if alt.exists():
            labels_path = alt
        else:
            raise FileNotFoundError(f"no {labels_name} in {corpus_dir}")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    records = []
    for entry in labels.get("files", []):
        file_path = corpus_dir / str(entry.get("file") or "")
        record = {
            "file": str(entry.get("file") or ""),
            "shape": str(entry.get("shape") or ""),
            "sealed": bool(entry.get("sealed")),
        }
        if record["sealed"] and not open_holdout:
            record["status"] = "SEALED — holdout, opened exactly once at the end (spec §6)"
            records.append(record)
            continue
        if not file_path.exists():
            record["status"] = "MISSING FILE"
            records.append(record)
            continue
        detected = detect_names(file_path)
        record.update(score_names(list(entry.get("expected_students") or []), detected))
        record["status"] = "scored"
        records.append(record)
    return records


def format_report(records: list[dict], *, show_names: bool = False) -> str:
    """Counts-only by default (privacy: real corpora carry real names)."""
    lines = []
    lines.append(f"{'file':44.44s} {'shape':26.26s} {'exp':>4s} {'det':>4s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'prec':>6s} {'rec':>6s}")
    for r in records:
        if r.get("status") != "scored":
            lines.append(f"{r['file']:44.44s} {r['shape']:26.26s} {r['status']}")
            continue
        prec = "n/a" if r["precision"] is None else f"{r['precision']:.2f}"
        rec = "n/a" if r["recall"] is None else f"{r['recall']:.2f}"
        lines.append(
            f"{r['file']:44.44s} {r['shape']:26.26s} {r['expected_count']:>4d} "
            f"{r['detected_count']:>4d} {r['true_positives']:>4d} {r['false_positives']:>4d} "
            f"{r['false_negatives']:>4d} {prec:>6s} {rec:>6s}"
        )
        if show_names:
            if r["false_positive_names"]:
                lines.append(f"    FP: {', '.join(r['false_positive_names'])}")
            if r["false_negative_names"]:
                lines.append(f"    FN: {', '.join(r['false_negative_names'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus_dir", type=Path,
                        help="directory holding the labelled files + labels.json")
    parser.add_argument("--open-holdout", action="store_true",
                        help="score sealed files too — this is a one-time, end-of-wave action (spec §6)")
    parser.add_argument("--show-names", action="store_true",
                        help="print FP/FN names (local/private use only — never paste real names into shared docs)")
    args = parser.parse_args(argv)
    records = score_corpus(args.corpus_dir, open_holdout=args.open_holdout)
    print(format_report(records, show_names=args.show_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
