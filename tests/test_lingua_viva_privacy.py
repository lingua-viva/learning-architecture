from pathlib import Path

import pytest

from src.lingua_viva import privacy


def test_private_paths_reuse_doctor_rules():
    assert privacy.is_private_path(Path("data/student_lens.db"))
    assert privacy.is_private_path("Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx")
    assert not privacy.is_private_path("curriculum/lingua_viva_matrix.yaml")


def test_redacts_runtime_private_context():
    text = "student name: Marco Rossi, parent: Lucia Rossi, email marco@example.com"

    redacted = privacy.redact_runtime_text(text)

    assert "Marco Rossi" not in redacted
    assert "Lucia Rossi" not in redacted
    assert "marco@example.com" not in redacted
    assert "[REDACTED_PRIVATE_CONTEXT]" in redacted
    assert "[REDACTED_EMAIL]" in redacted


def test_assert_safe_for_external_output_blocks_student_context():
    with pytest.raises(ValueError):
        privacy.assert_safe_for_external_output("student observation: needs support")


def test_assert_safe_for_external_output_allows_public_curriculum_language():
    text = "Grade 3 curriculum is designed to target CEFR A1 language functions."

    assert privacy.assert_safe_for_external_output(text) == text


def test_runtime_privacy_applies_declared_pii_patterns():
    text = "Email a@example.com or call +39 1234567890. MRN: 123456."

    redacted = privacy.redact_runtime_text(text)

    assert "a@example.com" not in redacted
    assert "+39 1234567890" not in redacted
    assert "123456" not in redacted
    assert privacy.contains_private_runtime_data(text) is True
