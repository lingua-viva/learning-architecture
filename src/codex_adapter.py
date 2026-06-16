"""
Backwards compatibility — codex_adapter is now agent_adapter.

All logic lives in agent_adapter.py. This file re-exports for
existing imports (mc_cli.py, tests) that reference codex_adapter.
"""

from src.agent_adapter import (  # noqa: F401
    AgentEnvelopeStore as CodexEnvelopeStore,
    sanitize_source_query,
    infer_files_to_read,
    task_envelope_from_pipeline_result,
    summarize_results,
    load_result_file,
)
