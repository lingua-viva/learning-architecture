# Integration Onboarding (IO) — forced-convergence loop tool
#
# Ported from mission-canvas's MC-GOV-009 build (2026-07-14). Forced-
# convergence interview for deciding how a new messaging-bot / agent
# integration is governed BEFORE anything is wired. Modeled on the
# phase-gated shape (state dict, save/load, an explicit `decide()` that
# forces an operator choice before the state machine advances) but kept
# generalized: this tool must work for ANY future integration case, not
# just the one that motivated the original build. Output is config, not
# code — it picks between the two existing patterns in this repo
# (bridges/<platform>_bridge.py vs src/education/slack_bot.py's governed-
# capture shape) and emits a structured integration_config +
# bridge_wiring_record, it does not generate bespoke per-case
# integration code.
import os
import yaml
import hashlib
from datetime import datetime
from pathlib import Path

MC_ROOT = Path(__file__).parent.parent

# Phases
PHASE_PURPOSE = 0      # Phase 0: free-text capture of what the bot is for
PHASE_PATTERN = 1      # Phase 1: bridge vs capture — operator decides explicitly
PHASE_SCOPE = 2        # Phase 2: platform, channel allowlist, output destination
PHASE_GOVERNANCE = 3   # Phase 3: blocks_external / requires_local — operator approves
PHASE_ASSEMBLY = 4     # Phase 4: emit integration_config + bridge_wiring_record
PHASE_VERIFY = 5       # Phase 5: representative-query smoke check
PHASE_DONE = 6         # Phase 6: complete

PHASE_NAMES = {
    PHASE_PURPOSE: "Purpose",
    PHASE_PATTERN: "Pattern Selection",
    PHASE_SCOPE: "Scope",
    PHASE_GOVERNANCE: "Governance",
    PHASE_ASSEMBLY: "Assembly",
    PHASE_VERIFY: "Verify",
    PHASE_DONE: "Done",
}

# Keyword signals used to ground the PATTERN recommendation in what the
# purpose text actually describes — not a hardcoded per-customer branch.
_BRIDGE_SIGNALS = [
    "conversational", "real-time", "real time", "query", "ask", "chat",
    "back-and-forth", "back and forth", "q&a", "qa", "question", "respond",
]
_CAPTURE_SIGNALS = [
    "capture", "log", "record", "transcript", "observation", "append-only",
    "append only", "archive", "store", "webhook",
]

# Known bridge files in this repo's bridges/ directory — used to check
# whether a named platform actually has a bridge before recommending it.
_KNOWN_BRIDGE_PLATFORMS = [
    "slack", "discord", "email", "signal", "teams", "whatsapp", "telegram",
]


class IntegrationOnboarding:
    def __init__(self, onboarding_id=None, base_dir=None):
        self.base_dir = base_dir or str(MC_ROOT)
        self.onboarding_id = onboarding_id
        self.state = {
            "onboarding_id": onboarding_id,
            "current_phase": PHASE_PURPOSE,
            "purpose": {
                "description": "",
                "captured_at": "",
            },
            "pattern": {
                "options": [],
                "decision": None,
                "reasoning": None,
            },
            "scope": {
                "platform": None,
                "channels": [],
                "output_destination": None,
            },
            "governance": {
                "options": [],
                "blocks_external": None,
                "requires_local": None,
                "decision": None,
                "rationale": None,
                "approved": False,
            },
            "artifacts": {
                "integration_config": "",
                "bridge_wiring_record": "",
            },
            "verify": {
                "smoke_query": "",
                "result": None,   # "pass" | "fail"
                "notes": "",
            },
            "decision_log": [],
        }

    # ---- persistence -----------------------------------------------

    def get_onboarding_dir(self):
        if not self.onboarding_id:
            return None
        return os.path.join(self.base_dir, "scratch", "onboarding", self.onboarding_id)

    def save(self):
        onboarding_dir = self.get_onboarding_dir()
        if not onboarding_dir:
            return
        os.makedirs(onboarding_dir, exist_ok=True)
        state_file = os.path.join(onboarding_dir, "onboarding_state.yaml")
        with open(state_file, "w") as f:
            yaml.safe_dump(self.state, f, sort_keys=False)

    def load(self, onboarding_id):
        self.onboarding_id = onboarding_id
        onboarding_dir = self.get_onboarding_dir()
        state_file = os.path.join(onboarding_dir, "onboarding_state.yaml")
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                self.state = yaml.safe_load(f)
            return True
        return False

    @staticmethod
    def list_all(base_dir=None):
        base_dir = base_dir or str(MC_ROOT)
        onboarding_root = os.path.join(base_dir, "scratch", "onboarding")
        if not os.path.exists(onboarding_root):
            return []
        ids = []
        for name in os.listdir(onboarding_root):
            if name.startswith("IO-") and os.path.isdir(os.path.join(onboarding_root, name)):
                ids.append(name)
        return sorted(ids)

    # ---- Phase 0: PURPOSE --------------------------------------------

    def start(self, purpose_text):
        timestamp = datetime.now().strftime("%Y%m%d")
        h = hashlib.md5(purpose_text.encode("utf-8")).hexdigest()[:6]
        self.onboarding_id = f"IO-{timestamp}-{h}"
        self.state["onboarding_id"] = self.onboarding_id
        self.state["purpose"]["description"] = purpose_text
        self.state["purpose"]["captured_at"] = datetime.now().isoformat()

        onboarding_dir = self.get_onboarding_dir()
        os.makedirs(onboarding_dir, exist_ok=True)

        self.state["current_phase"] = PHASE_PATTERN
        self._propose_pattern()
        self.save()
        return self.onboarding_id

    # ---- Phase 1: PATTERN ----------------------------------------------

    def _propose_pattern(self):
        text = self.state["purpose"]["description"].lower()
        bridge_hits = [s for s in _BRIDGE_SIGNALS if s in text]
        capture_hits = [s for s in _CAPTURE_SIGNALS if s in text]

        if len(bridge_hits) > len(capture_hits):
            recommended = "BRIDGE"
            signal_note = f"Signals detected favoring conversational bridge: {', '.join(bridge_hits)}."
        elif len(capture_hits) > len(bridge_hits):
            recommended = "CAPTURE"
            signal_note = f"Signals detected favoring governed capture: {', '.join(capture_hits)}."
        else:
            recommended = None
            signal_note = "No strong signal either way in the purpose text — operator judgment required."

        self.state["pattern"]["options"] = [
            {
                "id": "BRIDGE",
                "description": (
                    "Conversational Bridge: real-time back-and-forth query/answer, modeled on "
                    "bridges/<platform>_bridge.py (BaseBridge contract, channel allowlist, "
                    "mention-requirement, thread replies). This repo ships bridges for: "
                    f"{', '.join(_KNOWN_BRIDGE_PLATFORMS)}."
                ),
                "offers": "Fits a case where users ask questions and expect an answer in the thread.",
                "recommended": recommended == "BRIDGE",
            },
            {
                "id": "CAPTURE",
                "description": (
                    "Governed Capture: append-only structured capture with a fixed governance "
                    "boundary, modeled on src/education/slack_bot.py (Events API webhook receiver, "
                    "signed-request verification, tag-based capture, never echoes content back, "
                    "never calls an external model)."
                ),
                "offers": "Fits a case where the bot observes and records, and never engages in dialogue.",
                "recommended": recommended == "CAPTURE",
            },
        ]
        self.state["pattern"]["signal_note"] = signal_note

    def get_pattern_decision(self):
        if self.state["current_phase"] != PHASE_PATTERN:
            return None
        return self.state["pattern"]

    def decide_pattern(self, option_id, reasoning):
        if self.state["current_phase"] != PHASE_PATTERN:
            return False, "Not currently in the Pattern Selection phase."
        option_id = option_id.upper()
        valid_ids = [opt["id"] for opt in self.state["pattern"]["options"]]
        if option_id not in valid_ids:
            return False, f"Invalid option {option_id}. Valid choices are: {', '.join(valid_ids)}"

        self.state["pattern"]["decision"] = option_id
        self.state["pattern"]["reasoning"] = reasoning
        self._log_decision("PATTERN", option_id, reasoning)

        self.state["current_phase"] = PHASE_SCOPE
        self.save()
        return True, f"Pattern decided: {option_id}. Progressed to Scope phase."

    # ---- Phase 2: SCOPE --------------------------------------------------

    def set_scope(self, platform, channels, output_destination):
        if self.state["current_phase"] != PHASE_SCOPE:
            return False, "Not currently in the Scope phase."
        if not platform:
            return False, "Platform is required (e.g. slack)."
        if not output_destination:
            return False, "Output destination is required (e.g. local_store, existing_pipeline, both)."

        self.state["scope"]["platform"] = platform
        self.state["scope"]["channels"] = channels or []
        self.state["scope"]["output_destination"] = output_destination
        self._log_decision(
            "SCOPE",
            output_destination,
            f"platform={platform}, channels={channels or []}, destination={output_destination}",
        )

        self.state["current_phase"] = PHASE_GOVERNANCE
        self._propose_governance()
        self.save()
        return True, "Scope recorded. Progressed to Governance phase."

    # ---- Phase 3: GOVERNANCE ----------------------------------------------

    def _propose_governance(self):
        # Default-conservative: an unset or ambiguous boundary must default
        # to local_only / blocks_external, never permissive by default.
        destination = self.state["scope"]["output_destination"] or ""
        crosses_boundary = destination in ("existing_pipeline", "both") or (
            self.state["pattern"]["decision"] == "BRIDGE"
        )

        self.state["governance"]["options"] = [
            {
                "id": "CONSERVATIVE",
                "description": "blocks_external: true, requires_local: true — no data from this integration leaves the local boundary.",
                "offers": "The safe default. Correct unless the case has an explicit, named reason to widen it.",
                "recommended": True,
            },
            {
                "id": "WIDEN",
                "description": "blocks_external: false — this integration may route specific, named data externally under an explicit condition you must state.",
                "offers": (
                    "Only correct if the case genuinely requires external routing "
                    "(e.g. an external model answering conversational queries). "
                    "Requires a named boundary, not a guess."
                ),
                "recommended": False,
            },
        ]
        self.state["governance"]["_crosses_boundary_hint"] = crosses_boundary

    def get_governance_decision(self):
        if self.state["current_phase"] != PHASE_GOVERNANCE:
            return None
        return self.state["governance"]

    def decide_governance(self, option_id, rationale):
        if self.state["current_phase"] != PHASE_GOVERNANCE:
            return False, "Not currently in the Governance phase."
        option_id = option_id.upper()
        valid_ids = [opt["id"] for opt in self.state["governance"]["options"]]
        if option_id not in valid_ids:
            return False, f"Invalid option {option_id}. Valid choices are: {', '.join(valid_ids)}"
        if not rationale or len(rationale.strip()) < 10:
            return False, "Governance decisions require a stated rationale (min 10 characters) — an unset boundary must default conservative, never be guessed."

        if option_id == "CONSERVATIVE":
            self.state["governance"]["blocks_external"] = True
            self.state["governance"]["requires_local"] = True
        else:
            self.state["governance"]["blocks_external"] = False
            self.state["governance"]["requires_local"] = False

        self.state["governance"]["decision"] = option_id
        self.state["governance"]["rationale"] = rationale
        self.state["governance"]["approved"] = True
        self._log_decision("GOVERNANCE", option_id, rationale)

        self.state["current_phase"] = PHASE_ASSEMBLY
        self.save()
        return True, f"Governance boundary decided: {option_id}. Progressed to Assembly phase."

    # ---- Phase 4: ASSEMBLY ------------------------------------------------

    def run_assembly(self):
        if self.state["current_phase"] != PHASE_ASSEMBLY:
            return False, "Not currently in the Assembly phase."
        if not self.state["governance"]["approved"]:
            return False, "Cannot assemble: governance boundary is not yet operator-approved."

        onboarding_dir = self.get_onboarding_dir()

        integration_config = {
            "onboarding_id": self.onboarding_id,
            "purpose": self.state["purpose"]["description"],
            "pattern": self.state["pattern"]["decision"],
            "pattern_reasoning": self.state["pattern"]["reasoning"],
            "scope": {
                "platform": self.state["scope"]["platform"],
                "channels": self.state["scope"]["channels"],
                "output_destination": self.state["scope"]["output_destination"],
            },
            "governance": {
                "blocks_external": self.state["governance"]["blocks_external"],
                "requires_local": self.state["governance"]["requires_local"],
                "rationale": self.state["governance"]["rationale"],
                "approved": self.state["governance"]["approved"],
            },
            "generated_at": datetime.now().isoformat(),
        }
        config_path = os.path.join(onboarding_dir, "integration_config.yaml")
        with open(config_path, "w") as f:
            yaml.safe_dump(integration_config, f, sort_keys=False)
        self.state["artifacts"]["integration_config"] = config_path

        wiring_md = self._render_wiring_record(integration_config)
        wiring_path = os.path.join(onboarding_dir, "BRIDGE_WIRING_RECORD.md")
        with open(wiring_path, "w") as f:
            f.write(wiring_md)
        self.state["artifacts"]["bridge_wiring_record"] = wiring_path

        self.state["current_phase"] = PHASE_VERIFY
        self.save()
        return True, "Assembled integration_config + bridge_wiring_record."

    def _render_wiring_record(self, cfg):
        platform = cfg["scope"]["platform"] or "<platform>"
        lines = [
            f"# Bridge Wiring Record — {self.onboarding_id}",
            "",
            f"**Purpose**: {cfg['purpose']}",
            f"**Pattern**: {cfg['pattern']}",
            f"**Platform**: {cfg['scope']['platform']}",
            f"**Channels**: {', '.join(cfg['scope']['channels']) if cfg['scope']['channels'] else '(none specified)'}",
            f"**Output destination**: {cfg['scope']['output_destination']}",
            f"**Governance**: blocks_external={cfg['governance']['blocks_external']}, "
            f"requires_local={cfg['governance']['requires_local']}",
            f"**Rationale**: {cfg['governance']['rationale']}",
            "",
        ]
        if cfg["pattern"] == "BRIDGE":
            bridge_file = f"bridges/{platform}_bridge.py"
            bridge_exists_note = (
                "" if platform in _KNOWN_BRIDGE_PLATFORMS
                else f" **Known gap**: no bridge file found for platform '{platform}' in bridges/ — "
                     f"a new bridge must be built following the existing BaseBridge contract before this can wire."
            )
            lines += [
                "## Wiring steps (Conversational Bridge pattern)",
                "",
                f"1. Base contract: `{bridge_file}` (platform-specific bridge, `BaseBridge`).{bridge_exists_note}",
                "2. Configure channel allowlist from `scope.channels` above.",
                "3. Enforce mention-requirement and thread-reply behavior per the bridge's existing contract.",
                "4. If governance widened the boundary (blocks_external: false), confirm the exact "
                "external destination and data crossing it before going live.",
            ]
        else:
            lines += [
                "## Wiring steps (Governed Capture pattern)",
                "",
                "1. Base contract: `src/education/slack_bot.py` "
                "(Events API webhook receiver, signed-request verification).",
                "2. Extract and tag-parse the transcript per the existing `extract_transcript` / "
                "tag-parsing pattern — never guess an identity from absence.",
                "3. Deduplicate by `event_id` before any side effect.",
                "4. Write only to the local store named in `scope.output_destination` above — "
                "never echo content back, never call an external model.",
                "5. This pattern defaults `blocks_external: true` — if governance widened it, "
                "re-confirm that's actually intended for a capture-only integration.",
            ]
        lines.append("")
        return "\n".join(lines)

    # ---- Phase 5: VERIFY ---------------------------------------------------

    def run_verify(self, smoke_query, result, notes=""):
        if self.state["current_phase"] != PHASE_VERIFY:
            return False, "Not currently in the Verify phase."
        result = result.lower()
        if result not in ("pass", "fail"):
            return False, "Result must be 'pass' or 'fail'."

        self.state["verify"]["smoke_query"] = smoke_query
        self.state["verify"]["result"] = result
        self.state["verify"]["notes"] = notes
        self._log_decision("VERIFY", result, notes or smoke_query)

        if result == "pass":
            self.state["current_phase"] = PHASE_DONE
            self.save()
            return True, "Smoke check passed. Integration onboarding complete."
        else:
            self.save()
            return True, "Smoke check failed — remains in Verify phase. Re-run 'mc onboard verify' after fixing the wiring."

    # ---- shared -------------------------------------------------------

    def _log_decision(self, phase_name, decision, reasoning):
        self.state["decision_log"].append({
            "phase": phase_name,
            "decision": decision,
            "reasoning": reasoning,
            "decided_at": datetime.now().isoformat(),
        })
