"""Shared fixtures for the Lingua Viva eval suite.

The eval suite tests PROPERTIES, not mechanisms. Tests that are live exercise
existing code against the perfect-state spec. Skipped tests await implementation.
"""

import sys
from pathlib import Path

# Ensure src/ is importable from nested eval directories
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest
import yaml


EVALS_DIR = Path(__file__).parent
FIXTURES_DIR = EVALS_DIR / "fixtures"
SCHEMAS_DIR = EVALS_DIR / "layer1_schema" / "schemas"


@pytest.fixture
def fixtures_dir():
    """Path to the eval fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def schemas_dir():
    """Path to the JSON schema directory."""
    return SCHEMAS_DIR


@pytest.fixture
def synthetic_students():
    """Load the synthetic student roster."""
    with open(FIXTURES_DIR / "synthetic_students.yaml") as f:
        data = yaml.safe_load(f)
    return data["students"]


@pytest.fixture
def synthetic_observations():
    """Load synthetic observations."""
    with open(FIXTURES_DIR / "synthetic_observations.yaml") as f:
        data = yaml.safe_load(f)
    return data["observations"]


@pytest.fixture
def canaries():
    """Load canary values for isolation testing."""
    with open(FIXTURES_DIR / "synthetic_students.yaml") as f:
        data = yaml.safe_load(f)
    return data["canaries"]


@pytest.fixture
def teacher_history_dir():
    """Path to synthetic teacher history fixtures."""
    return FIXTURES_DIR / "synthetic_teacher_history"
