# Lingua Viva Teacher Readiness

- Run timestamp: `2026-08-03T18:07:59.298583Z`
- Git SHA: `06f98d3`
- Duration: `134039 ms`
- Readiness: `84.2%` (16/19 checks passed)
- Highest severity: `P1`

| Chain | Check | Status | Severity | Expected fail | Evidence |
|---|---|---|---|---|---|
| preflight | DR Single shared external-model routing predicate | PASS | - | no | `{"locations": ["src/pipeline.py:264:_is_external_model = staticmethod(is_external_model)", "src/pipeline.py:323:self._is_external_model(resolved_model)", "src/lingua_viva/reasoning.py:68:self._is_external_model(resolv...` |
| probe | C2 Voice probe availability matches import recheck | PASS | - | no | `{"imports_available": true, "probe_available": true, "status": 200}` |
| probe | C11 Functional probe parity covers STT import | PASS | - | no | `{"av_import": true, "faster_whisper_import": true}` |
| observe_ask | C1 No bracket placeholder reaches Observe -> Ask | PASS | - | no | `{"placeholder_match": null}` |
| observe_ask | C3 No-model response is teacher-facing, not a stub | PASS | - | no | `{"model_used": null, "status": 200}` |
| observe_ask | C4 GIR/tone values are coherent when present | PASS | - | no | `{"gir": null, "voice_tone": null}` |
| observe_ask | C8 Observe -> Ask latency envelope | PASS | - | no | `{"duration_ms": 62526}` |
| observe_materials | C1 No bracket placeholder reaches materials | PASS | - | no | `{}` |
| observe_materials | C8 Observe -> Materials route completes inside latency envelope | FAIL | P1 | no | `{"capture_status": 200, "duration_ms": 60375, "materials_error": "generation_failed", "materials_status": 422}` |
| observe_parent_report | C1 No bracket placeholder reaches parent report | PASS | - | no | `{}` |
| observe_parent_report | C6 Parent report source observation ids belong to student | FAIL | P1 | no | `{"capture_observation_id": "c7a2590d-de1a-4db2-a7d4-860787b43706", "known_observation_ids": ["7c463b4e-7e61-4a07-a9e5-b17ecb98be4a", "c7a2590d-de1a-4db2-a7d4-860787b43706"], "source_observation_ids": []}` |
| observe_parent_report | C8 Observe -> Parent report latency envelope | PASS | - | no | `{"duration_ms": 372, "status": 200}` |
| cold_ask | C5 Cold Ask does not invent observations | PASS | - | no | `{"response_preview": "{\"_status_code\": 200, \"classification\": {\"confidence\": 0.7, \"domain\": \"intents\", \"name\": \"research\", \"node\": \"intent-research\"}, \"duration_ms\": 28, \"external_calls\": 0, \"gi...` |
| cold_ask | C8 Cold Ask latency envelope | PASS | - | no | `{"duration_ms": 736}` |
| double_artifact | C7 Repeated save produces one record | FAIL | P2 | no | `{"created_count": 2, "first_status": 200, "second_status": 200}` |
| zero_egress | ZE Zero-egress controls have scoped firewall evidence | PASS | - | no | `{"scoped_log_counts": {"teacher-readiness-TR-ZE-001": 1, "teacher-readiness-TR-ZE-002": 1}, "unexpected_socket_hosts": []}` |
| invention_probe | INV Every cited observation identifier exists | PASS | - | no | `{"cited_ids": [], "invented_ids": [], "known_observation_ids": ["54f02ff8-ce64-43d5-b78b-be9017277b2f", "dddfde71-4a3d-4c7b-87b9-71a758748ad0"]}` |
| model_failure | C9 Ollama-down degradation does not mix no-model with deterministic output | PASS | - | no | `{"banner_seen": true, "has_deterministic_terms": true, "has_no_model": false, "model_used": "none:deterministic_only", "sentinel_seen": true}` |
| model_failure | C10 Fake non-listed provider is blocked local with warning and zero egress | PASS | - | no | `{"external_calls": 0, "model_used": "ollama/qwen2.5:7b", "status": 200}` |

## Clean-Run Criteria

A clean run has zero P0/P1 failures, zero placeholders on teacher-facing surfaces, scoped zero-egress firewall evidence for every negative control, and no expected-fail items remaining after companion Track 1/Track 3 fixes land.

This command is report-only. It does not gate releases yet.
