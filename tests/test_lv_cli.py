import json

from src.lingua_viva import cli
from src.lingua_viva.reasoning import ReasonResult


def test_health_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "provider_status", lambda: {
        "connected": False,
        "provider": "local",
        "model": None,
        "ollama_reachable": True,
    })

    assert cli.main(["health", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["provider"] == "local"
    assert output["ollama_reachable"] is True


def test_ingest_rejects_non_pdf(capsys):
    assert cli.main(["ingest", "notes.txt"]) == 2

    assert "PDF files only" in capsys.readouterr().out


def test_doctor_subcommand(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_doctor", lambda: {
        "status": "OK",
        "summary": "Everything looks healthy.",
        "checks": [],
        "next_steps": [],
    })
    monkeypatch.setattr(cli, "format_teacher_summary", lambda result: "Lingua Viva Doctor: OK")

    assert cli.main(["doctor"]) == 0

    assert "Lingua Viva Doctor: OK" in capsys.readouterr().out


def test_chat_subcommand(monkeypatch, capsys):
    async def fake_reason(self, query, context=None, model=None, default_model=None, system_prompt=None):
        return ReasonResult(content=f"reply to {query}", confidence=0.75, model_used="test")

    monkeypatch.setattr("src.lingua_viva.cli.ReasoningEngine.reason", fake_reason)

    assert cli.main(["chat", "ciao"]) == 0

    assert "reply to ciao" in capsys.readouterr().out
