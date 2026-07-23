from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(
    encoding="utf-8"
)


def test_both_voice_surfaces_use_shared_oka_runtime():
    assert "voiceRuntime.toggleObserve();" in HTML
    assert 'voiceRuntime.toggleAsk()' in HTML
    assert "recognition.interimResults = true;" in HTML
    assert "}, 2500);" in HTML


def test_voice_errors_cannot_submit_a_preexisting_typed_draft():
    assert "this.gotSpeech ? this.finalText.trim()" in HTML
    assert "if (text && !hadError)" in HTML
    assert 'this.recognitionError = event.error || "unknown";' in HTML


def test_voice_callbacks_tolerate_navigation_away():
    assert 'get(id) {' in HTML
    assert 'const input = this.get("ask-input");' in HTML
    assert "if (input) input.value" in HTML
    assert 'const mic = this.get("ask-mic");' in HTML


def test_ask_prevents_overlapping_voice_queries_and_does_not_speak_errors():
    assert "if (!text || voiceRuntime.busy) return;" in HTML
    assert "voiceRuntime.busy = true;" in HTML
    assert "voiceRuntime.busy = false;" in HTML
    assert "if (fromVoice && !data.error)" in HTML


def test_observe_requires_human_review_before_save():
    assert '<option value="">Choose after review</option>' in HTML
    assert 'if (!templateType)' in HTML
    assert 'templateType === "cefr"' in HTML
    assert '$("obs-urgency").checked = false;' in HTML
    assert "suggested — check to affirm" in HTML


def test_observe_keeps_manual_fallback_and_save_errors_visible():
    assert "No reliable suggestions. Choose the fields manually." in HTML
    assert "Local model unavailable. Continue with manual fields." in HTML
    assert "The local save failed. Your text is still in the form." in HTML
    assert 'button.disabled = false;' in HTML


def test_voice_controls_and_statuses_are_accessible():
    assert 'aria-label="Start observation speech capture"' in HTML
    assert 'id="mic-status" class="badge" aria-live="polite"' in HTML
    assert 'aria-label="Talk to Lingua Viva" aria-pressed="false"' in HTML
    assert 'id="ask-voice-status" class="voice-hint" aria-live="polite"' in HTML
