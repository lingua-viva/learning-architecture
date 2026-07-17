import json

from src.lingua_viva import config


def test_detect_model_picks_best_installed_model():
    assert config.detect_model(["qwen2.5:7b", "qwen3:8b"]) == "ollama/qwen3:8b"


def test_detect_model_falls_back_to_cloud_when_ollama_has_no_preferred_models():
    assert config.detect_model(["tiny-custom"]) == "ollama/kimi-k2.7-code:cloud"


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


def test_connect_provider_rejects_non_string_model(monkeypatch, tmp_path):
    monkeypatch.setenv("LV_CONFIG_HOME", str(tmp_path))

    result = config.connect_provider("openai", "sk-test", model=123)

    assert result["status"] == "rejected"
    assert not config.provider_config_path().exists()
