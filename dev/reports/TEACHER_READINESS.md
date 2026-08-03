# Lingua Viva Teacher Readiness

- Run timestamp: `2026-08-03T23:04:03.728046Z`
- Git SHA: `30d4cac`
- Duration: `345090 ms`
- Readiness: `68.4%` (13/19 checks passed)
- Highest severity: `P0`

| Chain | Check | Status | Severity | Expected fail | Evidence |
|---|---|---|---|---|---|
| preflight | DR Single shared external-model routing predicate | PASS | - | no | `{"locations": ["src/pipeline.py:275:_is_external_model = staticmethod(is_external_model)", "src/pipeline.py:338:self._is_external_model(resolved_model)", "src/lingua_viva/reasoning.py:80:self._is_external_model(resolv...` |
| probe | C2 Voice probe availability matches import recheck | PASS | - | no | `{"imports_available": true, "probe_available": true, "status": 200}` |
| probe | C11 Functional probe parity covers STT import | PASS | - | no | `{"av_import": true, "faster_whisper_import": true}` |
| observe_ask | C1 No bracket placeholder reaches Observe -> Ask | PASS | - | no | `{"placeholder_match": null}` |
| observe_ask | C3 No-model response is teacher-facing, not a stub | PASS | - | no | `{"model_used": null, "status": 200}` |
| observe_ask | C4 GIR/tone values are coherent when present | PASS | - | no | `{"gir": null, "voice_tone": null}` |
| observe_ask | C8 Observe -> Ask latency envelope | PASS | - | no | `{"duration_ms": 62208}` |
| observe_materials | C1 No bracket placeholder reaches materials | PASS | - | no | `{}` |
| observe_materials | C8 Observe -> Materials route completes inside latency envelope | FAIL | P1 | no | `{"capture_status": 200, "duration_ms": 60383, "materials_error": "generation_failed", "materials_status": 422}` |
| observe_parent_report | C1 No bracket placeholder reaches parent report | PASS | - | no | `{}` |
| observe_parent_report | C6 Parent report source observation ids belong to student | FAIL | P1 | no | `{"capture_observation_id": "e7056407-6957-454b-abdc-1aa7d126f54f", "known_observation_ids": ["8e09b253-3d22-438c-885a-a4f94331eb00", "e7056407-6957-454b-abdc-1aa7d126f54f"], "source_observation_ids": []}` |
| observe_parent_report | C8 Observe -> Parent report latency envelope | PASS | - | no | `{"duration_ms": 361, "status": 200}` |
| cold_ask | C5 Cold Ask does not invent observations | PASS | - | no | `{"response_preview": "{\"_status_code\": 200, \"error\": \"that took longer than expected \\u2014 the local ai model may still be loading. wait a few seconds and ask again.\", \"timeout\": true, \"timestamp\": 1785798...` |
| cold_ask | C8 Cold Ask latency envelope | PASS | - | no | `{"duration_ms": 60850}` |
| double_artifact | C7 Repeated save produces one record | FAIL | P2 | no | `{"created_count": 2, "first_status": 200, "second_status": 200}` |
| zero_egress | ZE Zero-egress controls have scoped firewall evidence | FAIL | P0 | no | `{"scoped_log_counts": {"teacher-readiness-TR-ZE-001": 4, "teacher-readiness-TR-ZE-002": 4}, "unexpected_socket_hosts": []}` |
| invention_probe | INV Every cited observation identifier exists | PASS | - | no | `{"cited_ids": [], "invented_ids": [], "known_observation_ids": ["7fd2cbbb-157c-4902-acb8-4faff0ec9923", "bb93780f-2b15-4491-a9f6-38807885b944"]}` |
| model_failure | C9 Ollama-down degradation does not mix no-model with deterministic output | FAIL | P1 | yes | `{"banner_seen": false, "has_deterministic_terms": false, "has_no_model": false, "model_used": null, "sentinel_seen": false}` |
| model_failure | C10 Fake non-listed provider is blocked local with warning and zero egress | FAIL | P0 | yes | `{"external_calls": null, "model_used": null, "status": 200}` |

## Clean-Run Criteria

A clean run has zero P0/P1 failures, zero placeholders on teacher-facing surfaces, scoped zero-egress firewall evidence for every negative control, and no expected-fail items remaining after companion Track 1/Track 3 fixes land.

This command is report-only. It does not gate releases yet.
