#!/usr/bin/env python3
"""GIR + Voice Real-App Hardening Harness.

Posts synthetic teacher questions to a running LV app and captures
observability evidence for the hardening report.

Usage:
    python3 scripts/run_lv_voice_gir_hardening.py [--url http://127.0.0.1:8787]

Outputs JSONL evidence to dev/reports/artifacts/gir_voice_hardening_evidence.jsonl
and a summary to stdout.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("FATAL: httpx is required. Install project test dependencies before running this harness.")
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO / "dev" / "reports" / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_PATH = ARTIFACTS_DIR / "gir_voice_hardening_evidence.jsonl"

# --- Scenario definitions ---

SCENARIOS = [
    # Bucket: strong local curriculum coverage (3)
    {"id": 1, "bucket": "strong_local", "question": "What should Grade 3 students practice for Italian listening this week?"},
    {"id": 2, "bucket": "strong_local", "question": "How should I introduce classroom greetings to beginners?"},
    {"id": 3, "bucket": "strong_local", "question": "What evidence should I collect before moving a student to more independent speaking?"},
    # Bucket: thin/no local source coverage (3)
    {"id": 4, "bucket": "thin_source", "question": "What is the school's policy for lunch supervision on rainy days?"},
    {"id": 5, "bucket": "thin_source", "question": "Which bus route should a new family take to campus tomorrow?"},
    {"id": 6, "bucket": "thin_source", "question": "Explain something Lingua Viva probably cannot know: the latest local train disruption near school."},
    # Bucket: student-support/synthetic names (3)
    {"id": 7, "bucket": "student_support", "question": "Student Alpha is a synthetic student. How should I support their confidence in speaking?"},
    {"id": 8, "bucket": "student_support", "question": "Student Beta is a synthetic student. Draft a cautious next step for their listening practice."},
    {"id": 9, "bucket": "student_support", "question": "Student Gamma is a synthetic student. What should I tell their family about progress?"},
    # Bucket: admin/operations (2)
    {"id": 10, "bucket": "admin_ops", "question": "What Slack daily operations messages should I expect from the assistant?"},
    {"id": 11, "bucket": "admin_ops", "question": "How do I confirm a Google Drive import became an extraction source?"},
    # Bucket: follow-up/context (2)
    {"id": 12, "bucket": "followup", "question": "Follow up: make that answer shorter and teacher-ready."},
    {"id": 13, "bucket": "followup", "question": "Follow up: what source did you rely on most?"},
    # Bucket: streaming/voice stress (2)
    {"id": 14, "bucket": "stress", "question": "Give me a three-sentence plan for a mixed-level Italian class."},
    {"id": 15, "bucket": "stress", "question": "What does Lingua Viva know about the IB MYP language acquisition guide?"},
]


def _try_stream(client: httpx.Client, question: str, timeout: float = 30.0) -> dict:
    """Try /api/query/stream first, fall back to /api/query."""
    evidence: dict = {"route_attempted": "/api/query/stream", "sse_events": [], "stream_ok": False}
    try:
        with client.stream(
            "POST", "/api/query/stream",
            json={"query": question, "intent": "TEACH"},
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"status {resp.status_code}", request=resp.request, response=resp
                )
            evidence["stream_ok"] = True
            final_result = None
            sentences = []
            event_type = "message"
            for line in resp.iter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    event_type = line[len("event:"):].strip()
                    evidence["sse_events"].append(event_type)
                elif line.startswith("data:"):
                    data_str = line[len("data:"):].strip()
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if event_type == "result" or data.get("type") == "result" or "classification" in data:
                        final_result = data
                    if event_type == "answer_sentence" or data.get("type") == "answer_sentence":
                        sentences.append(data.get("text") or data.get("sentence") or "")
                    if event_type == "error" or data.get("type") == "error":
                        evidence["stream_error_event"] = data.get("error") or "stream error"
                    # Also check for top-level result-like data
                    if "gir_score" in data and final_result is None:
                        final_result = data
            evidence["sentences_received"] = len(sentences)
            evidence["first_sentence"] = sentences[0][:100] if sentences else ""
            if final_result:
                evidence["route_used"] = "/api/query/stream"
                return {**evidence, **_extract_fields(final_result)}
    except Exception as exc:
        evidence["stream_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    # Fallback to /api/query
    evidence["route_attempted"] = "/api/query (fallback)"
    try:
        resp = client.post("/api/query", json={"query": question, "intent": "TEACH"}, timeout=timeout)
        data = resp.json()
        evidence["route_used"] = "/api/query"
        return {**evidence, **_extract_fields(data)}
    except Exception as exc:
        evidence["fallback_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        evidence["route_used"] = "failed"
        return evidence


def _extract_fields(data: dict) -> dict:
    """Extract the observability fields from a query response."""
    grounding = data.get("grounding") or {}
    gir = grounding.get("gir") or {}
    classification = data.get("classification") or {}
    result = data.get("result") or {}
    return {
        "answer_preview": str(result.get("content") or data.get("content") or "")[:200],
        "classification_node": classification.get("node") or "",
        "classification_domain": classification.get("domain") or "",
        "classification_confidence": classification.get("confidence"),
        "gir_score": data.get("gir_score") or gir.get("score"),
        "gir_method": data.get("gir_method") or gir.get("method") or "",
        "voice_tone": data.get("voice_tone") or "",
        "tone_prefix": data.get("tone_prefix") or "",
        "grounding_tier_used": grounding.get("tier_used") or "",
        "route": data.get("route") or "",
        "model_used": data.get("model_used") or "",
        "external_calls": data.get("external_calls"),
        "sources": data.get("sources") or [],
        "trace_id": data.get("trace_id") or "",
        "duration_ms": data.get("duration_ms"),
        "error": data.get("error"),
    }


def _try_tts(client: httpx.Client, text: str, tone_prefix: str = "") -> dict:
    """Try TTS and capture the result without requiring Rime."""
    tts_evidence: dict = {"tts_attempted": True}
    try:
        body: dict = {"text": text[:500]}
        if tone_prefix:
            body["tone_prefix"] = tone_prefix
        resp = client.post("/api/voice/tts", json=body, timeout=10.0)
        tts_evidence["tts_status"] = resp.status_code
        if resp.status_code == 200:
            tts_evidence["tts_result"] = "audio"
            tts_evidence["tts_content_type"] = resp.headers.get("content-type", "")
            tts_evidence["tts_bytes"] = len(resp.content)
        elif resp.status_code == 403:
            body_json = resp.json()
            tts_evidence["tts_result"] = "privacy_refusal"
            tts_evidence["tts_fallback"] = body_json.get("fallback")
            tts_evidence["tts_violations"] = body_json.get("violations")
        elif resp.status_code == 503:
            tts_evidence["tts_result"] = "rime_unavailable"
        else:
            tts_evidence["tts_result"] = f"error_{resp.status_code}"
            try:
                tts_evidence["tts_error"] = resp.json().get("error", "")
            except Exception:
                pass
    except Exception as exc:
        tts_evidence["tts_result"] = "exception"
        tts_evidence["tts_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return tts_evidence


def _privacy_tts_probe(client: httpx.Client) -> dict:
    """Use the seeded demo roster to prove named-student TTS stays local."""
    try:
        roster = client.get("/api/students", timeout=10.0).json().get("students") or []
        display_name = ""
        if roster:
            display_name = str(roster[0].get("display_name") or roster[0].get("student_id") or "").strip()
        if not display_name:
            return {"privacy_probe": "unavailable", "privacy_probe_reason": "no demo roster name"}
        response = client.post(
            "/api/voice/tts",
            json={"text": f"{display_name} is a synthetic roster student making progress."},
            timeout=10.0,
        )
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "privacy_probe": "pass" if response.status_code == 403 and body.get("fallback") == "local" else "fail",
            "privacy_probe_status": response.status_code,
            "privacy_probe_fallback": body.get("fallback"),
        }
    except Exception as exc:
        return {
            "privacy_probe": "error",
            "privacy_probe_error": f"{type(exc).__name__}: {str(exc)[:200]}",
        }


def run_scenario(client: httpx.Client, scenario: dict) -> dict:
    """Run one scenario and return full evidence."""
    started = time.time()
    evidence = {
        "scenario_id": scenario["id"],
        "bucket": scenario["bucket"],
        "question": scenario["question"],
        "timestamp": time.time(),
    }

    # Query
    query_result = _try_stream(client, scenario["question"])
    evidence.update(query_result)

    # TTS probe — use the first sentence or the answer preview
    tts_text = query_result.get("first_sentence") or query_result.get("answer_preview") or ""
    tone_prefix = query_result.get("tone_prefix") or ""
    if tts_text:
        tts_evidence = _try_tts(client, tts_text, tone_prefix)
        evidence.update(tts_evidence)
    else:
        evidence["tts_attempted"] = False
        evidence["tts_result"] = "no_text_to_speak"
    if scenario["bucket"] == "student_support":
        evidence.update(_privacy_tts_probe(client))

    evidence["elapsed_s"] = round(time.time() - started, 2)
    return evidence


def classify_verdict(ev: dict) -> str:
    """Quick verdict based on evidence."""
    if ev.get("error"):
        return "ERROR"
    if ev.get("route_used") == "failed":
        return "BLOCKED"
    answer_preview = str(ev.get("answer_preview") or "")
    answer_lower = answer_preview.lower()
    if not answer_preview:
        return "NO_ANSWER"
    # Degraded-state phrasings: legacy placeholder ("no model available"),
    # breaker message, and the teacher-facing setup messages from
    # src/lingua_viva/messages.py (P1-2 fix).
    if (
        "no model available" in answer_lower
        or "ollama appears to be down" in answer_lower
        or "i need a local ai model" in answer_lower
        or "no local model is available" in answer_lower
    ):
        return "BLOCKED"

    gir = ev.get("gir_score")
    tone = ev.get("voice_tone") or ""
    prefix = ev.get("tone_prefix") or ""

    issues = []
    if gir is not None:
        if gir >= 0.8 and tone != "plain":
            issues.append("tone_mismatch_high_gir")
        if gir < 0.4 and tone == "plain":
            issues.append("overconfident_low_gir")
        if gir < 0.8 and not prefix:
            issues.append("missing_hedge_prefix")

    if ev.get("tts_result") == "privacy_refusal" and ev["bucket"] != "student_support":
        issues.append("unexpected_privacy_block")
    if ev["bucket"] == "student_support" and ev.get("privacy_probe") != "pass":
        issues.append("privacy_probe_not_refused")

    if issues:
        return f"ISSUES: {', '.join(issues)}"
    return "OK"


def main():
    url = os.environ.get("LV_APP_URL", "http://127.0.0.1:8787")
    if len(sys.argv) > 2 and sys.argv[1] == "--url":
        url = sys.argv[2]

    print(f"GIR + Voice Hardening Harness")
    print(f"App URL: {url}")
    print(f"Evidence: {EVIDENCE_PATH}")
    print("=" * 70)

    client = httpx.Client(base_url=url, timeout=35.0)

    # Verify app is up
    try:
        r = client.get("/")
        assert r.status_code == 200
    except Exception as exc:
        print(f"FATAL: app not reachable at {url}: {exc}")
        sys.exit(1)

    # Seed demo roster for privacy gate testing. The names returned by this
    # local demo endpoint are synthetic fixtures, not live student data.
    client.get("/api/students")

    results = []
    with open(EVIDENCE_PATH, "w", encoding="utf-8") as f:
        for scenario in SCENARIOS:
            print(f"\n[{scenario['id']:02d}/{len(SCENARIOS)}] {scenario['bucket']}: {scenario['question'][:60]}...")
            evidence = run_scenario(client, scenario)
            verdict = classify_verdict(evidence)
            evidence["verdict"] = verdict
            results.append(evidence)
            f.write(json.dumps(evidence) + "\n")
            f.flush()

            gir = evidence.get("gir_score", "?")
            tone = evidence.get("voice_tone", "?")
            tts = evidence.get("tts_result", "?")
            route = evidence.get("route_used", "?")
            print(f"    route={route} gir={gir} tone={tone} tts={tts} -> {verdict} ({evidence.get('elapsed_s', '?')}s)")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok = sum(1 for r in results if r["verdict"] == "OK")
    blocked = sum(1 for r in results if r["verdict"] == "BLOCKED")
    issues = [r for r in results if r["verdict"].startswith("ISSUES")]
    errors = [r for r in results if r["verdict"] in ("ERROR", "NO_ANSWER")]

    print(f"  OK:      {ok}/{len(results)}")
    print(f"  ISSUES:  {len(issues)}/{len(results)}")
    print(f"  BLOCKED: {blocked}/{len(results)}")
    print(f"  ERRORS:  {len(errors)}/{len(results)}")

    if issues:
        print("\nISSUES:")
        for r in issues:
            print(f"  #{r['scenario_id']} ({r['bucket']}): {r['verdict']}")

    if errors:
        print("\nERRORS:")
        for r in errors:
            print(f"  #{r['scenario_id']} ({r['bucket']}): {r.get('error') or r['verdict']}")

    client.close()


if __name__ == "__main__":
    main()
