"""
Mission Canvas Gates — Entry and Exit

Entry Gate: Local LLM detects PII/PHI/sensitive data at FIRST CONTACT.
            Nothing sensitive ever makes it into a formulated query.

Exit Gate:  Socket firewall controls what leaves and what comes back.
            Only approved hosts. All attempts logged.

Mission Canvas sits between the gates as memory and context engine.
"""

from .entry import EntryGate, SensitivityReport
from .exit import ExitGate

__all__ = ["EntryGate", "SensitivityReport", "ExitGate"]
