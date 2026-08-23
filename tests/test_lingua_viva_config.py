import json

from src.lingua_viva import config


def test_detect_model_picks_best_installed_model():
    assert config.detect_model(["qwen2.5:7b", "qwen3:8b"]) == "ollama/qwen3:8b"


def test_detect_model_qwen3_is_quality_floor():
    assert config.detect_model(["qwen3:8b"]) == "ollama/qwen3:8b"


def test_detect_model_fails_closed_when_no_preferred_local_model_installed():
    # STEP 8 (L10): a LOCAL-model detector must never answer with a cloud
    # model. The old ollama/<cloud> last resort meant "detect local" could
    # silently become "send to cloud".
    assert config.detect_model(["tiny-custom"]) is None


def test_detect_model_never_returns_a_cloud_model_class_lock():
    """Class-lock (spec §3 STEP 8): detector output never matches ':cloud' —
    for any installed set, including one where ONLY cloud models exist."""
    import inspect

    cloud_only = ["kimi-k2.6:cloud", "kimi-k2.7-code:cloud"]
    assert config.detect_model(cloud_only) is None
    mixed = cloud_only + ["qwen2.5:7b", "qwen3:8b"]
    picked = config.detect_model(mixed)
    assert picked == "ollama/qwen3:8b"
    assert ":cloud" not in (picked or "")
    # Source-level: no cloud fallback path may reappear inside detect_model.
    assert ":cloud" not in inspect.getsource(config.detect_model)


def test_detect_model_prefers_resident_fit_over_larger_offloaded(monkeypatch):
    """STEP 8 (C1): with live sizes known, a model that fits estimated GPU
    memory beats a preference-earlier model that would run CPU-offloaded
    [MC-measured: ~4s prefill + 29ms/token offloaded vs ~100ms + 0.1ms/token
    resident]. Setup: 6GB GPU with qwen3:8b and qwen2.5:14b installed."""
    installed = ["qwen2.5:14b", "qwen3:8b"]
    monkeypatch.setattr(config, "list_ollama_models", lambda: list(installed))
    monkeypatch.setattr(
        config, "_ollama_model_sizes",
        lambda: {"qwen2.5:14b": int(9.0e9), "qwen3:8b": int(5.2e9)},
    )
    monkeypatch.setattr(config, "_estimate_gpu_gb", lambda: 6.0)  # 5.4GB budget

    assert config.detect_model() == "ollama/qwen3:8b"

    # With enough GPU for the larger old model, the qwen3 quality floor still
    # wins because qwen2.5 models are retained only as legacy fallbacks.
    monkeypatch.setattr(config, "_estimate_gpu_gb", lambda: 16.0)
    assert config.detect_model() == "ollama/qwen3:8b"

    # Callers passing installed names (no sizes) keep pure preference order.
    assert config.detect_model(installed) == "ollama/qwen3:8b"


# --- STEP 7 (SPEC_LV_UNIFIED_REAL_DATA_FIX 2026-08-19, L6): ONE model normalizer


def test_model_matches_installed_handles_latest_tagless_and_case():
    installed = {"Nemotron-3.5-Lightning:latest", "qwen2.5:7b"}
    assert config.model_matches_installed("nemotron-3.5-lightning", installed)
    assert config.model_matches_installed("NEMOTRON-3.5-LIGHTNING:latest", installed)
    assert config.model_matches_installed("qwen2.5", installed)  # tagless vs any tag
    assert config.model_matches_installed("qwen2.5:7b", installed)
    assert not config.model_matches_installed("qwen2.5:3b", installed)
    assert not config.model_matches_installed("", installed)
    assert not config.model_matches_installed("qwen2.5:7b", set())


def test_detector_pick_always_passes_the_privacy_gate(monkeypatch):
    """THE L6 regression: with 'X:latest' installed, detect_model picks
    'ollama/X'. The gate's exact-membership check refused that pick, so
    every student-data call died as none:local_only while the enrichment
    layer blamed 'invalid JSON'. Detector and gate must share one matcher."""
    from src.lingua_viva import model_gate

    installed = ["nemotron-3.5-lightning:latest", "qwen2.5:7b"]
    picked = config.detect_model(installed)
    assert picked is not None and picked.startswith("ollama/")

    monkeypatch.delenv("LV_LOCAL_MODEL_ALLOWLIST", raising=False)
    monkeypatch.setattr(config, "list_ollama_models", lambda: list(installed))
    model_gate.clear_model_gate_cache()
    try:
        assert model_gate.is_provably_local_model(picked) is True
    finally:
        model_gate.clear_model_gate_cache()


def test_one_model_normalizer_class_lock():
    """Class-lock (spec §3 STEP 7): fails if a second normalization path
    appears. The ':latest' handling may live ONLY inside
    config.model_matches_installed, and model_gate must route its installed
    check through that exact function."""
    import inspect
    from pathlib import Path

    from src.lingua_viva import model_gate

    canonical = inspect.getsource(config.model_matches_installed)
    config_src = Path(config.__file__).read_text(encoding="utf-8")
    gate_src = Path(model_gate.__file__).read_text(encoding="utf-8")

    assert ":latest" in canonical
    assert config_src.count(":latest") == canonical.count(":latest")
    assert ":latest" not in gate_src
    assert "model_matches_installed" in gate_src


def test_read_provider_config_survives_bad_json(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    path = config.provider_config_path()
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2, 3]")

    assert config.read_provider_config() is None
    assert config.resolve_provider_model() is None


def test_provider_status_treats_ollama_as_local(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    path = config.provider_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "providers": {"ollama": {"model": "qwen3:8b"}},
        "default_provider": "ollama",
    }))
    monkeypatch.setattr(config, "ollama_reachable", lambda: True)

    assert config.provider_status() == {
        "connected": False,
        "provider": "local",
        "model": "qwen3:8b",
        "ollama_reachable": True,
    }


def test_connect_provider_writes_verified_config(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(config, "verify_key", lambda provider, api_key, model: (True, "ok"))

    result = config.connect_provider("openai", "sk-test")

    assert result["status"] == "connected"
    saved = json.loads(config.provider_config_path().read_text())
    assert saved["providers"]["openai"]["api_key"] == "sk-test"
    assert saved["providers"]["openai"]["model"] == "gpt-4o-mini"
    assert saved["default_provider"] == "openai"


def test_service_keys_save_without_disturbing_reasoning_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    path = config.provider_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"model": "gpt-4o-mini", "api_key": "sk-test"}},
    }), encoding="utf-8")

    status = config.save_service_api_keys({
        "perplexity": "pplx-test",
        "rime": "rime-test",
    })

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["providers"]["openai"]["api_key"] == "sk-test"
    assert saved["perplexity_api_key"] == "pplx-test"
    assert saved["rime_api_key"] == "rime-test"
    assert status == {
        "perplexity": {"configured": True},
        "rime": {"configured": True},
    }
    assert config.service_api_key("perplexity") == "pplx-test"
    assert config.service_api_key("rime") == "rime-test"


def test_service_key_status_never_returns_plaintext(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))
    config.save_service_api_keys({"perplexity": "pplx-secret"})

    status = config.service_key_status()

    assert status == {
        "perplexity": {"configured": True},
        "rime": {"configured": False},
    }
    assert "pplx-secret" not in json.dumps(status)


def test_connect_provider_rejects_non_string_model(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))

    result = config.connect_provider("openai", "sk-test", model=123)

    assert result["status"] == "rejected"
    assert not config.provider_config_path().exists()
