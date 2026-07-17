from pathlib import Path
import sys


SUPPORT_ROOT = Path(__file__).resolve().parents[1]
DEV_ROOT = SUPPORT_ROOT.parent
sys.path.insert(0, str(DEV_ROOT))

from support_loop.privacy import matches_private_path, redact_text
from support_loop.schemas import CheckResult, worst_status
from support_loop.doctor import FORBIDDEN_README_PATTERNS, REQUIRED_CLAIMS, run_doctor


def test_redacts_common_sensitive_values():
    text = "email a.teacher@example.com token=sk-abcdefghijklmnopqrstuvwxyz phone 415-555-1212"
    redacted = redact_text(text)
    assert "a.teacher@example.com" not in redacted
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "415-555-1212" not in redacted


def test_private_paths_are_excluded():
    assert matches_private_path("case-studies/data/student_lens.db")
    assert matches_private_path("reports/IEP-alex.pdf")
    assert matches_private_path("Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx")
    assert not matches_private_path("README.md")


def test_worst_status_orders_privacy_above_blocked():
    checks = [
        CheckResult("a", "OK", "ok"),
        CheckResult("b", "BLOCKED", "blocked"),
        CheckResult("c", "PRIVATE_RISK", "private"),
    ]
    assert worst_status(checks) == "PRIVATE_RISK"


def test_doctor_returns_phase_a_contract():
    result = run_doctor(write_log=False)
    assert result["status"] in {"OK", "WARN", "FIXABLE", "UPDATE_AVAILABLE", "BLOCKED", "PRIVATE_RISK"}
    assert result["support_bundle_available"] is False
    assert result["external_calls"] is False
    assert isinstance(result["checks"], list)
    assert {check["id"] for check in result["checks"]} >= {
        "branch",
        "lv_artifact_gauntlet",
        "revision_log_schema",
        "matrix_authority",
        "claim_register",
        "publication_safety",
        "readme_overclaims",
        "docx_no_diff",
        "active_surface_mc_bloat",
        "privacy_path_scan",
    }


def test_forbidden_readme_patterns_cover_required_overclaims():
    joined = "\n".join(FORBIDDEN_README_PATTERNS)
    for phrase in (
        "unique globally",
        "no existing curriculum integrates",
        "students achieve CEFR",
        "students reach CEFR",
        "validated outcomes",
        "publication is guaranteed",
    ):
        assert phrase in joined


def test_required_claim_set_contains_phase_a_claims():
    assert "lv-claim-global-uniqueness" in REQUIRED_CLAIMS
    assert "lv-claim-cefr-a1-b1-progression" in REQUIRED_CLAIMS
