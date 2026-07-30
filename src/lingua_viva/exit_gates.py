from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EXTERNAL_DESTINATIONS = {
    "openai",
    "groq",
    "mistral",
    "ollama:cloud",
    "rime",
    "google_drive",
    "governance_export",
}

SUPPORTED_SURFACES = {
    "reasoning",
    "tts",
    "drive_upload",
    "governance_export",
}

STUDENT_DATA_EXTERNAL_BLOCKED = "student_data_external_blocked"
PUBLICATION_SAFETY_BLOCKED = "publication_safety_blocked"
UNSAFE_PATH_BLOCKED = "unsafe_path_blocked"
UNSUPPORTED_DESTINATION = "unsupported_destination"
EMPTY_PAYLOAD_BLOCKED = "empty_payload_blocked"


@dataclass(frozen=True)
class ExitRequest:
    surface: str
    destination: str
    payload_text: str = ""
    file_paths: tuple[str, ...] = ()
    student_ids: tuple[str, ...] = ()
    student_names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    allow_scrubbed: bool = False


@dataclass(frozen=True)
class ExitDecision:
    allowed: bool
    blocked_reason: str = ""
    scrubbed_text: str = ""
    violations: tuple[dict[str, Any], ...] = ()
    external: bool = True
    audit_event: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocked_reason": self.blocked_reason,
            "scrubbed_text": self.scrubbed_text,
            "violations": list(self.violations),
            "external": self.external,
            "audit_event": self.audit_event,
        }


def _destination_key(destination: str) -> str:
    candidate = (destination or "local").strip().lower()
    if candidate.startswith(("openai/", "openai")):
        return "openai"
    if candidate.startswith(("groq/", "groq")):
        return "groq"
    if candidate.startswith(("mistral/", "mistral")):
        return "mistral"
    if ":cloud" in candidate:
        return "ollama:cloud"
    if candidate in {"rime", "google_drive", "governance_export", "local"}:
        return candidate
    return candidate


def _is_external(destination: str) -> bool:
    return _destination_key(destination) in EXTERNAL_DESTINATIONS


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def _violation(rule: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **extra}


def _path_allowed(raw_path: str, roots: tuple[str, ...]) -> bool:
    if not raw_path or not roots:
        return False
    try:
        resolved = Path(raw_path).expanduser().resolve(strict=False)
    except OSError:
        return False
    for raw_root in roots:
        try:
            root = Path(raw_root).expanduser().resolve(strict=False)
        except OSError:
            continue
        if root == resolved or root in resolved.parents:
            return True
    return False


def log_exit_decision(request: ExitRequest, decision: ExitDecision) -> None:
    """Record the decision without raw text or full paths.

    privacy_log intentionally genericizes detail for display, so the structural
    fields here are reduced to hashed/count metadata before becoming query_text.
    """
    try:
        from src.lingua_viva.privacy_log import log_event

        material = {
            "surface": request.surface,
            "destination": _destination_key(request.destination),
            "reason": decision.blocked_reason,
            "payload_hash": _hash_value(request.payload_text),
            "file_count": len(request.file_paths),
            "student_id_count": len(request.student_ids),
            "student_name_count": len(request.student_names),
        }
        event_type = decision.audit_event or ("exit_gate_allowed" if decision.allowed else "exit_gate_blocked")
        log_event(event_type, query_text=repr(sorted(material.items())))
    except Exception:
        return


class ExitGate:
    def check(self, request: ExitRequest) -> ExitDecision:
        surface = (request.surface or "").strip().lower()
        destination = _destination_key(request.destination)
        external = _is_external(destination)

        if surface not in SUPPORTED_SURFACES:
            return ExitDecision(
                allowed=False,
                blocked_reason=UNSUPPORTED_DESTINATION,
                violations=(_violation("exit_gate.surface", "Unsupported exit surface."),),
                external=external,
                audit_event="exit_gate_blocked",
            )

        if not external:
            return ExitDecision(allowed=True, external=False, audit_event="exit_gate_allowed")

        if destination not in EXTERNAL_DESTINATIONS:
            return ExitDecision(
                allowed=False,
                blocked_reason=UNSUPPORTED_DESTINATION,
                violations=(_violation("exit_gate.destination", "Unsupported external destination."),),
                external=True,
                audit_event="exit_gate_blocked",
            )

        if surface in {"reasoning", "tts"} and not request.payload_text.strip():
            return ExitDecision(
                allowed=False,
                blocked_reason=EMPTY_PAYLOAD_BLOCKED,
                violations=(_violation("exit_gate.payload", "Nothing was provided for the external call."),),
                external=True,
                audit_event="exit_gate_blocked",
            )

        if surface == "reasoning":
            return self._check_reasoning(request)
        if surface == "tts":
            return self._check_tts(request)
        if surface == "drive_upload":
            return self._check_drive_upload(request)
        if surface == "governance_export":
            return self._check_governance_export(request)
        return ExitDecision(allowed=True, external=external, audit_event="exit_gate_allowed")

    def _check_reasoning(self, request: ExitRequest) -> ExitDecision:
        if request.metadata.get("local_only"):
            return ExitDecision(
                allowed=False,
                blocked_reason=STUDENT_DATA_EXTERNAL_BLOCKED,
                violations=(_violation("privacy_rules.local_only", "Local-only content cannot be sent to an external model."),),
                external=True,
                audit_event="exit_gate_blocked",
            )
        if self._contains_student_data(request):
            return ExitDecision(
                allowed=False,
                blocked_reason=STUDENT_DATA_EXTERNAL_BLOCKED,
                violations=(_violation("privacy_rules.student_data", "Student or family data cannot be sent to an external model."),),
                external=True,
                audit_event="exit_gate_blocked",
            )
        return ExitDecision(allowed=True, scrubbed_text=request.payload_text, external=True, audit_event="exit_gate_allowed")

    def _check_tts(self, request: ExitRequest) -> ExitDecision:
        safety = self._publication_safety({"text": request.payload_text}, request.student_names)
        if safety.get("blocked"):
            return ExitDecision(
                allowed=False,
                blocked_reason=PUBLICATION_SAFETY_BLOCKED,
                violations=tuple(safety.get("violations") or ()),
                external=True,
                audit_event="exit_gate_blocked",
            )
        if self._contains_student_data(request):
            return ExitDecision(
                allowed=False,
                blocked_reason=STUDENT_DATA_EXTERNAL_BLOCKED,
                violations=(_violation("privacy_rules.student_data", "Student or family data cannot be sent to speech services."),),
                external=True,
                audit_event="exit_gate_blocked",
            )
        return ExitDecision(allowed=True, scrubbed_text=request.payload_text, external=True, audit_event="exit_gate_allowed")

    def _check_drive_upload(self, request: ExitRequest) -> ExitDecision:
        roots = tuple(str(item) for item in request.metadata.get("allowed_roots") or ())
        violations: list[dict[str, Any]] = []
        for raw_path in request.file_paths:
            if not _path_allowed(raw_path, roots):
                violations.append(
                    _violation(
                        "exit_gate.file_path",
                        "Only Lingua Viva deliverables can be shared externally.",
                        path_hash=_hash_value(str(raw_path)),
                    )
                )
        if violations:
            return ExitDecision(
                allowed=False,
                blocked_reason=UNSAFE_PATH_BLOCKED,
                violations=tuple(violations),
                external=True,
                audit_event="exit_gate_blocked",
            )
        if not request.file_paths:
            return ExitDecision(
                allowed=False,
                blocked_reason=EMPTY_PAYLOAD_BLOCKED,
                violations=(_violation("exit_gate.file_path", "No files were provided for upload."),),
                external=True,
                audit_event="exit_gate_blocked",
            )
        return ExitDecision(allowed=True, external=True, audit_event="exit_gate_allowed")

    def _check_governance_export(self, request: ExitRequest) -> ExitDecision:
        pack = request.metadata.get("pack")
        if isinstance(pack, dict):
            safety = self._publication_safety(pack, request.student_names)
        else:
            safety = self._publication_safety({"text": request.payload_text}, request.student_names)
        if safety.get("blocked"):
            return ExitDecision(
                allowed=False,
                blocked_reason=PUBLICATION_SAFETY_BLOCKED,
                violations=tuple(safety.get("violations") or ()),
                external=True,
                audit_event="exit_gate_blocked",
            )
        return ExitDecision(allowed=True, scrubbed_text=request.payload_text, external=True, audit_event="exit_gate_allowed")

    def _contains_student_data(self, request: ExitRequest) -> bool:
        text = request.payload_text or ""
        lowered = text.lower()
        for name in request.student_names:
            cleaned = (name or "").strip().lower()
            if len(cleaned) >= 3 and cleaned in lowered:
                return True
        if request.student_ids:
            return True
        try:
            from src.lingua_viva.privacy import contains_private_runtime_data

            return contains_private_runtime_data(text)
        except Exception:
            return bool(text.strip())

    def _publication_safety(self, pack: dict[str, Any], student_names: tuple[str, ...]) -> dict[str, Any]:
        try:
            from src.lingua_viva.governance import check_publication_safety

            return check_publication_safety(pack, student_names=list(student_names))
        except Exception:
            return {
                "blocked": True,
                "violations": [
                    _violation("exit_gate.publication_safety", "Publication safety could not be checked.")
                ],
            }


def check_exit(request: ExitRequest) -> ExitDecision:
    decision = ExitGate().check(request)
    log_exit_decision(request, decision)
    return decision
