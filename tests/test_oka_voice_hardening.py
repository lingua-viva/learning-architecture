from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(
    encoding="utf-8"
)


def test_both_voice_surfaces_use_shared_oka_runtime():
    assert 'id="voice-companion"' in HTML
    assert 'id="vc-mic"' in HTML
    assert "toggleVoiceCompanion" in HTML
    assert "captureLocalStt({" in HTML
    assert 'fetch("/api/voice/stt"' in HTML
    assert "Date.now() - lastSound > 2000" in HTML


def test_voice_errors_cannot_submit_a_preexisting_typed_draft():
    assert "if (!blob.size)" in HTML
    assert "onTranscript(transcript, data);" in HTML
    assert 'throw new Error(data.message || data.error || "transcription failed")' in HTML


def test_voice_callbacks_tolerate_navigation_away():
    assert 'get(id) {' in HTML
    assert "const input = this.get(inputId);" in HTML
    assert "if (input) input.value" in HTML
    assert "const mic = this.get(micId);" in HTML


def test_ask_prevents_overlapping_voice_queries_and_does_not_speak_errors():
    assert "if (!text || voiceRuntime.busy) return;" in HTML
    assert "voiceRuntime.busy = true;" in HTML
    assert "voiceRuntime.busy = false;" in HTML
    assert "if (fromVoice && !data.error)" in HTML


def test_observe_requires_human_review_before_save():
    # A4 (2026-08-04): type is optional — "general" is the default, not forced.
    # The human review gate is: student must be chosen + text must be present.
    assert '<option value="general">General</option>' in HTML
    assert 'templateType === "cefr"' in HTML
    assert '$("obs-urgency").checked = false;' in HTML
    assert "suggested — check to affirm" in HTML


def test_observe_keeps_manual_fallback_and_save_errors_visible():
    assert "No reliable suggestions. Choose the fields manually." in HTML
    assert "Local model unavailable. Continue with manual fields." in HTML
    assert "The local save failed. Your text is still in the form." in HTML
    assert 'button.disabled = false;' in HTML


def test_voice_controls_and_statuses_are_accessible():
    assert 'aria-label="Voice companion"' in HTML
    assert 'aria-label="Start voice input"' in HTML
    assert 'id="mic-status" class="badge" aria-live="polite"' in HTML
    assert 'id="ask-voice-status" class="voice-hint" aria-live="polite"' in HTML
