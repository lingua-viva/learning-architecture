from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional
from urllib import error, request


# qwen3:8b is the local quality floor (2026-08-22): qwen2.5:3b is small
# enough for broad hardware, but not capable enough for lesson plans/lenses.
# The native Ollama path now sends think=false for qwen3/nemotron-class models,
# so qwen3:8b no longer has the old hidden-token timeout failure mode.
LOCAL_MODEL_PREFERENCE = [
    "nemotron-3.5-lightning",  # 30B MoE, 3B active — 3.9x faster than dense on GPU
    "qwen3:8b",
    "qwen3:14b",
    "phi4:14b",
    "qwen2.5:14b",
    "llama3.1:8b",
    "qwen2.5:7b",
    "mistral:7b",
    "qwen2.5:3b",
]

# Models that declare the "thinking" capability: their visible answer is
# empty until reasoning finishes, which on slow hardware burns the whole
# timeout budget emitting hidden tokens. The native Ollama /api/chat request
# must send "think": false for these (STEP 8, C1 — MC-proven fix; only
# models with the capability accept the parameter).
THINKING_MODEL_TAGS = ("glm", "nemotron", "qwen3")


def is_thinking_model(model: str | None) -> bool:
    name = (model or "").strip().lower()
    return any(tag in name for tag in THINKING_MODEL_TAGS)


# ---------------------------------------------------------------------------
# Hardware-adaptive model selection (ported from Mission Canvas onboarding.py)
# ---------------------------------------------------------------------------
# Tier thresholds and model sizes verified against ollama.com/library.

_TIER_MODEL_MAP = {
    "ultra_gpu":  "qwen3:8b",       # default quality floor; larger models are opt-in
    "strong_gpu": "qwen3:8b",       # 5.2GB, minimum viable LV quality floor
    "mid_gpu":    "qwen3:8b",       # 5.2GB, fits M1 Pro 16GB with headroom
    "weak_gpu":   "qwen3:8b",       # quality floor; may be slower than 3B
    "cpu_only":   "qwen3:8b",       # quality floor; setup can still be skipped
}


def _estimate_gpu_gb() -> float:
    """Estimate usable GPU memory in GB without requiring Ollama.

    NVIDIA via nvidia-smi (all platforms), AMD via sysfs (Linux),
    Apple Silicon via unified memory. Falls through to 0.0 (cpu_only)."""
    # NVIDIA
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            return int(out.stdout.strip().splitlines()[0]) / 1e3  # MiB -> GB
    except Exception:
        pass
    # Windows AMD/Intel: display-class registry
    if platform.system() == "Windows":
        gb = _windows_gpu_gb()
        if gb > 0.0:
            return gb
    # Linux AMD: sysfs VRAM + GTT (APU) or VRAM-only (discrete)
    if platform.system() == "Linux":
        for card in sorted(Path("/sys/class/drm").glob("card*/device/mem_info_vram_total")):
            try:
                vram_gb = int(card.read_text().strip()) / 1e9
                gtt_path = card.parent / "mem_info_gtt_total"
                gtt_gb = int(gtt_path.read_text().strip()) / 1e9 if gtt_path.exists() else 0.0
                if gtt_gb > vram_gb:
                    return vram_gb + gtt_gb  # APU: inference spills into GTT
                else:
                    return vram_gb  # Discrete: VRAM-bandwidth-bound
            except (ValueError, OSError):
                continue
    # Apple Silicon: unified memory
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return _system_ram_gb()
    return 0.0


def _windows_gpu_gb() -> float:
    """Read GPU memory from Windows display-class registry (vendor-agnostic).
    Win32_VideoController.AdapterRAM is deliberately NOT used — it's a 32-bit
    value that caps at 4GB."""
    if platform.system() != "Windows":
        return 0.0
    try:
        import winreg
    except ImportError:
        return 0.0
    best = 0.0
    try:
        klass = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",
        )
    except OSError:
        return 0.0
    try:
        for i in range(64):
            try:
                subname = winreg.EnumKey(klass, i)
                sub = winreg.OpenKey(klass, subname)
                try:
                    val, _ = winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")
                    if isinstance(val, int) and val > 0:
                        best = max(best, val / 1e9)
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(sub)
            except OSError:
                continue
    finally:
        winreg.CloseKey(klass)
    return best


def _system_ram_gb() -> float:
    """Total physical RAM in GB."""
    try:
        if platform.system() == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return int(line.split()[1]) / 1e6
        elif platform.system() == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            return int(out.stdout.strip()) / 1e9
        else:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return stat.ullTotalPhys / 1e9
    except Exception:
        pass
    return 0.0


def gpu_tier() -> str:
    """Map detected GPU memory to a hardware tier."""
    gb = _estimate_gpu_gb()
    if gb >= 32:
        return "ultra_gpu"
    if gb >= 12:
        return "strong_gpu"
    if gb >= 6:
        return "mid_gpu"
    if gb >= 3:
        return "weak_gpu"
    return "cpu_only"


def recommended_model(installed_models: list[str] | None = None) -> str:
    """Return the default Ollama model for this machine's hardware.

    qwen3:8b is the minimum viable quality floor for LV workflows. Larger
    models such as nemotron can still be used when explicitly configured or
    detected as an installed fallback, but they are not the default pull."""
    tier = gpu_tier()
    return _TIER_MODEL_MAP.get(tier, "qwen3:8b")

SUPPORTED_PROVIDERS = {
    "openai": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
    },
    "groq": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.1-8b-instant",
    },
    "mistral": {
        "endpoint": "https://api.mistral.ai/v1/chat/completions",
        "default_model": "mistral-small-latest",
    },
}


def config_home() -> Path:
    home = os.environ.get("LV_CONFIG_HOME") or os.environ.get("SIR_CONFIG_HOME")
    return Path(home) if home else Path.home() / ".lingua-viva"


# Canonical home-resolution seam (MC-lessons §1): every module that stores
# local-first state under ~/.lingua-viva/ resolves its *default* location
# through this function. C8 durability (install-over-install keeps every
# lens) rests on this default sitting under the USER's home, never inside
# the app tree an installer replaces — pinned by
# tests/test_c8_install_over_install.py together with the additive-only
# store migration and the no-delete rule for install.sh / the desktop
# bootstrap. Change the default here and that promise moves with it.
#
# Every module that stores
# local-first state under ~/.lingua-viva/ resolves its *default* location
# through this function, so one env var (LV_CONFIG_HOME) — or one monkeypatch
# in tests/conftest.py — redirects all of it. Callers still expose their own
# more specific override (LV_TRACE_PATH, LV_PRIVACY_LOG_PATH, ...) which is
# checked first and wins when set explicitly.
def lv_home() -> Path:
    return config_home()


def provider_config_path() -> Path:
    return config_home() / "config" / "providers.json"


# Tier 2 school-configurable display (SPEC_LV_BASE_LENS_SCHOOL_CATEGORIES
# 2026-08-01): labels and visibility only. Category IDs are immutable —
# they are the schema contract existing SQLite lenses depend on, so they
# are never read from config (manifest-is-the-contract principle).
DEFAULT_SCHOOL_PROFILE = {
    "category_labels": {},
    "hidden_categories": ["advanced_enrichment"],
    # Multi-teacher triangulation (operator ruling 2026-08-01): colleague
    # teacher_ids render as full display names in the UI. The names live
    # here in Tier 2 config only — never in ledger filenames or any Drive
    # artifact. Unknown ids fall back to the raw teacher_id.
    "teacher_display_names": {},
    # This machine's teacher identity (operator ruling 2026-08-02, teacher-
    # identity P1): empty means un-provisioned, and every write falls back to
    # UNPROVISIONED_TEACHER_ID. Triangulation across machines requires each
    # machine to set a distinct id here (Settings → Teacher identity) —
    # ledgers authored under the un-provisioned default are never exported
    # to or imported from the shared folder, so two fresh installs can never
    # silently overwrite or misattribute each other's observations.
    "own_teacher_id": "",
}

# Reserved sentinel for a machine that has not set its teacher identity.
# Pre-dates the identity config (every web.py write path defaulted to it),
# so existing rows are backfilled by rename_local_teacher when an id is set.
UNPROVISIONED_TEACHER_ID = "local-teacher"


def own_teacher_id() -> str:
    """This machine's configured teacher id, or "" when un-provisioned."""
    return read_school_profile().get("own_teacher_id") or ""


def school_profile_path() -> Path:
    return config_home() / "config" / "school_profile.json"


def read_school_profile() -> dict:
    """Load per-school display config. Never raises: a missing, unreadable,
    or malformed file degrades to shipped defaults — a broken config file
    must not break the student lens view."""
    default = {
        "category_labels": dict(DEFAULT_SCHOOL_PROFILE["category_labels"]),
        "hidden_categories": list(DEFAULT_SCHOOL_PROFILE["hidden_categories"]),
        "teacher_display_names": dict(DEFAULT_SCHOOL_PROFILE["teacher_display_names"]),
        "own_teacher_id": str(DEFAULT_SCHOOL_PROFILE["own_teacher_id"]),
    }
    try:
        with school_profile_path().open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default
    if not isinstance(data, dict):
        return default
    labels = data.get("category_labels")
    if isinstance(labels, dict):
        default["category_labels"] = {
            str(key): str(value)
            for key, value in labels.items()
            if isinstance(key, str) and isinstance(value, str)
        }
    hidden = data.get("hidden_categories")
    if isinstance(hidden, list):
        default["hidden_categories"] = [
            item for item in hidden if isinstance(item, str)
        ]
    names = data.get("teacher_display_names")
    if isinstance(names, dict):
        default["teacher_display_names"] = {
            str(key): str(value)
            for key, value in names.items()
            if isinstance(key, str) and isinstance(value, str)
        }
    own = data.get("own_teacher_id")
    if isinstance(own, str):
        own = own.strip()
        # A hand-edited file claiming the reserved sentinel stays
        # un-provisioned — the sentinel is never a real identity.
        default["own_teacher_id"] = "" if own == UNPROVISIONED_TEACHER_ID else own
    return default


def read_provider_config() -> Optional[dict]:
    try:
        with provider_config_path().open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def provider_entries(config: dict) -> dict:
    providers = config.get("providers")
    return providers if isinstance(providers, dict) else {}


def provider_api_key(provider_name: str) -> Optional[str]:
    config = read_provider_config()
    if not config:
        return None
    entry = provider_entries(config).get(provider_name)
    return entry.get("api_key") if isinstance(entry, dict) else None


SERVICE_KEY_FIELDS = {
    "perplexity": "perplexity_api_key",
    "rime": "rime_api_key",
}


def service_api_key(service_name: str) -> Optional[str]:
    field = SERVICE_KEY_FIELDS.get(service_name)
    if not field:
        return None
    config = read_provider_config()
    if not config:
        return None
    value = config.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def service_key_status() -> dict:
    return {
        name: {"configured": bool(service_api_key(name))}
        for name in SERVICE_KEY_FIELDS
    }


def save_service_api_keys(keys: dict[str, str]) -> dict:
    """Persist non-reasoning service keys in providers.json.

    This intentionally does not verify the keys over the network: Ask and TTS
    already surface rejected credentials honestly at call time, and Settings
    must work offline for packaged installs.
    """
    allowed = {name: value for name, value in keys.items() if name in SERVICE_KEY_FIELDS}
    if not allowed:
        raise ValueError("No supported service keys were sent.")
    config_path = provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_provider_config() or {}
    for name, value in allowed.items():
        field = SERVICE_KEY_FIELDS[name]
        cleaned = str(value or "").strip()
        if cleaned:
            existing[field] = cleaned
        else:
            existing.pop(field, None)
    tmp_path = config_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(existing, handle)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, config_path)
    return service_key_status()


# The only providers Lingua Viva knows how to talk to (local Ollama plus
# the external SUPPORTED_PROVIDERS above). Anything else configured in
# providers.json is refused locally (see requested_blocked_provider),
# never silently ignored.
KNOWN_PROVIDER_NAMES = ("ollama", "openai", "groq", "mistral")


def resolve_provider_model() -> Optional[str]:
    config = read_provider_config()
    if not config:
        return None
    default_provider = config.get("default_provider")
    entry = provider_entries(config).get(default_provider)
    model_name = entry.get("model") if isinstance(entry, dict) else None
    if not model_name or not isinstance(model_name, str):
        return None
    if default_provider in KNOWN_PROVIDER_NAMES:
        return f"{default_provider}/{model_name}"
    return None


def requested_blocked_provider() -> Optional[str]:
    """Return the configured provider request when it names a provider that
    is not on the supported list (e.g. {"provider": "anthropic/claude-3.5"}).

    resolve_provider_model() returns None for these shapes, which used to
    mean an unsupported provider was silently ignored and the query fell
    through to normal model resolution with no warning (teacher-readiness
    C10). Surfacing the request lets the reasoning chokepoint refuse it
    locally with an explicit "blocked" message before any model is resolved.
    """
    config = read_provider_config()
    if not config:
        return None
    for key in ("provider", "default_provider"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        requested = value.strip()
        provider_name = requested.split("/", 1)[0].lower()
        if provider_name not in KNOWN_PROVIDER_NAMES:
            return requested
    return None


def list_ollama_models(timeout: int = 5) -> list[str]:
    req = request.Request("http://localhost:11434/api/tags", method="GET")
    with request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read())
    models = data.get("models", [])
    if not isinstance(models, list):
        return []
    names = [item.get("name") for item in models if isinstance(item, dict)]
    return [name for name in names if isinstance(name, str)]


def model_matches_installed(model: str, installed: set[str] | frozenset[str]) -> bool:
    """THE one installed-model matcher (STEP 7, SPEC_LV_UNIFIED_REAL_DATA_FIX
    2026-08-19, L6). Case-insensitive; handles the :latest suffix
    ('nemotron-3.5-lightning' matches 'nemotron-3.5-lightning:latest') and a
    tagless request against any tag of the base name.

    Both detect_model() and model_gate.is_provably_local_model() MUST route
    through this function. The 08-19 audit's L6 was these two disagreeing on
    ':latest': the detector picked a model the privacy gate then refused, so
    every student-data call died as none:local_only — and that refusal was
    misreported downstream as an invalid-JSON model response."""
    candidate = (model or "").strip().lower()
    if not candidate:
        return False
    normalized = {str(item).strip().lower() for item in installed}
    if candidate in normalized:
        return True
    if f"{candidate}:latest" in normalized:
        return True
    # Also match a tagless request against any tag of the base name
    if ":" not in candidate:
        return any(item.split(":")[0] == candidate for item in normalized)
    return False


# Fraction of estimated GPU memory a model file may occupy and still count
# as "resident" — the remainder is headroom for KV cache and context.
_RESIDENT_FIT_FRACTION = 0.9


def _ollama_model_sizes(timeout: int = 5) -> dict[str, int]:
    """Installed model name -> model file size in bytes, from /api/tags."""
    try:
        req = request.Request("http://localhost:11434/api/tags", method="GET")
        with request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
    except (error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
        return {}
    models = data.get("models", [])
    if not isinstance(models, list):
        return {}
    sizes: dict[str, int] = {}
    for item in models:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        try:
            sizes[item["name"]] = int(item.get("size") or 0)
        except (TypeError, ValueError):
            continue
    return sizes


def _candidate_size_bytes(candidate: str, sizes: dict[str, int]) -> int | None:
    """Size of the installed model this candidate names, resolved through THE
    matcher (model_matches_installed) so tag variants stay one concept."""
    for name, size in sizes.items():
        if size > 0 and model_matches_installed(candidate, {name}):
            return size
    return None


def detect_model(installed_models: list[str] | None = None) -> str | None:
    """Pick the best installed LOCAL model, or None — never a cloud model.

    Order: hardware-recommended model first, then LOCAL_MODEL_PREFERENCE.
    Among installed candidates, prefer one whose file fits in estimated GPU
    memory over a larger offloaded one (STEP 8, C1 — MC-measured: ~4s prefill
    + 29ms/token CPU-offloaded vs ~100ms + 0.1ms/token resident; residency
    matters more than model size). Sizes come from the live /api/tags probe;
    when a caller passes installed_models (names only, no sizes), every
    candidate is treated as fitting.

    STEP 8 (L10): fails closed. The old `ollama/<cloud>` last resort meant a
    LOCAL-model detector could quietly answer with a cloud route; callers that
    need a fallback must decide that themselves, in the open."""
    live_probe = installed_models is None
    try:
        installed = set(installed_models if installed_models is not None else list_ollama_models())
    except (error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    candidates: list[str] = []
    rec = recommended_model(list(installed))
    if model_matches_installed(rec, installed):
        candidates.append(rec)
    for model in LOCAL_MODEL_PREFERENCE:
        if model not in candidates and model_matches_installed(model, installed):
            candidates.append(model)
    if not candidates:
        return None
    if live_probe:
        sizes = _ollama_model_sizes()
        budget = _estimate_gpu_gb() * 1e9 * _RESIDENT_FIT_FRACTION
        if budget > 0 and sizes:
            for candidate in candidates:
                size = _candidate_size_bytes(candidate, sizes)
                if size is not None and size <= budget:
                    return f"ollama/{candidate}"
    return f"ollama/{candidates[0]}"


def ollama_reachable() -> bool:
    try:
        with request.urlopen("http://localhost:11434/api/tags", timeout=3):
            return True
    except (error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def ollama_embedding_reachable(model: str = "nomic-embed-text", timeout: int = 3) -> bool:
    payload = json.dumps({"model": model, "prompt": "probe"}).encode("utf-8")
    req = request.Request(
        "http://localhost:11434/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read())
        embedding = body.get("embedding")
        return isinstance(embedding, list) and bool(embedding)
    except (error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
        return False


def provider_status() -> dict:
    config = read_provider_config() or {}
    default_provider = config.get("default_provider")
    entry = provider_entries(config).get(default_provider) if default_provider else None
    if not isinstance(entry, dict):
        entry = None
    is_external = default_provider in SUPPORTED_PROVIDERS
    return {
        "connected": bool(entry and is_external),
        "provider": default_provider if (entry and is_external) else "local",
        "model": entry.get("model") if entry else None,
        "ollama_reachable": ollama_reachable(),
    }


def verify_key(provider: str, api_key: str, model: str) -> tuple[bool, str]:
    if provider not in SUPPORTED_PROVIDERS:
        return False, "unsupported"
    endpoint = SUPPORTED_PROVIDERS[provider]["endpoint"]
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15):
            return True, "ok"
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "bad_key"
        return False, "network"
    except (error.URLError, ConnectionError, TimeoutError, OSError):
        return False, "network"


def connect_provider(provider: str, api_key: str, model: Optional[str] = None) -> dict:
    if provider not in SUPPORTED_PROVIDERS:
        return {"status": "rejected", "message": "Unsupported provider."}
    if not (api_key or "").strip():
        return {"status": "rejected", "message": "This key didn't work - check it and try again."}
    if model is not None and not isinstance(model, str):
        return {"status": "rejected", "message": "Unsupported model value."}

    model = model or SUPPORTED_PROVIDERS[provider]["default_model"]
    ok, reason = verify_key(provider, api_key, model)
    if not ok and reason == "bad_key":
        return {"status": "rejected", "message": "This key didn't work - check it and try again."}

    config_path = provider_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_provider_config() or {}
    providers = provider_entries(existing)
    existing["providers"] = providers
    providers[provider] = {"model": model, "api_key": api_key, "verified": ok}
    existing["default_provider"] = provider

    tmp_path = config_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(existing, handle)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, config_path)

    if ok:
        return {"status": "connected", "message": f"Connected to {provider}."}
    return {"status": "saved_unreachable", "message": f"Saved - will use local mode until we can reach {provider}."}


def disconnect_provider() -> None:
    """Remove external provider config, preserving service keys (perplexity, rime).

    The old implementation deleted the entire file, which nuked perplexity and
    rime API keys set via Settings — a teacher disconnecting 'groq' shouldn't
    lose their Ask configuration."""
    config = read_provider_config()
    if not config:
        return
    # Preserve service-key fields
    preserved = {}
    for field in SERVICE_KEY_FIELDS.values():
        val = config.get(field)
        if isinstance(val, str) and val.strip():
            preserved[field] = val
    if not preserved:
        provider_config_path().unlink(missing_ok=True)
        return
    # Write back only the service keys
    config_path = provider_config_path()
    tmp_path = config_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(preserved, handle)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, config_path)
