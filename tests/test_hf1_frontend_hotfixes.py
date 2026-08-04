"""HF1 frontend hotfixes (Chip QA 0.2.32, 2026-08-04).

F2/FM-B  — renderAnswerSafety() is the single safety gate for text + voice.
F1b/FM-D — guaranteed mic hardware release, independent of the silence interval.
F5/FM-F  — no auto-selected student on any record-target select.
§8.2     — global voice companion hidden for day one (backend untouched).
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")


# --- F2: one safety gate, two consumers ---------------------------------------

def test_render_answer_safety_defined_once():
    assert HTML.count("function renderAnswerSafety(") == 1


def test_text_renderer_consumes_safety_gate():
    # The bubble prepends the warning and restyles the GIR badge.
    assert "${safety.warningHtml}<p>${escapeHtml(message.text)}</p>" in HTML
    assert 'class="${safety.girBadgeClass}">GIR' in HTML


def test_voice_paths_consume_safety_gate():
    # No speak/speakQueue call passes a raw tone_prefix anymore.
    assert "voiceRuntime.speak(reply.text, data.tone_prefix" not in HTML
    assert "voiceRuntime.speak(reply.text, result.tone_prefix" not in HTML
    assert "speakQueue([sentence], data.tone_prefix" not in HTML
    assert HTML.count(".speechPrefix") >= 4


def test_fabrication_warning_text_present():
    assert "I could not verify this against real records" in HTML


# --- F1b: guaranteed mic release ----------------------------------------------

def test_mic_release_listeners_registered():
    assert 'document.addEventListener("visibilitychange"' in HTML
    assert 'window.addEventListener("beforeunload"' in HTML
    assert "voiceRuntime.cleanupCapture()" in HTML


def test_mic_hard_duration_cap():
    assert "this.maxCaptureTimer = setTimeout(() => this.stopCapture(), 30000)" in HTML
    # Cleared on both stop paths.
    assert HTML.count("clearTimeout(this.maxCaptureTimer)") == 2


# --- F5: no auto-selected student ---------------------------------------------

def test_no_first_student_auto_select():
    assert "state.selectedStudent = state.students[0].student_id" not in HTML


def test_stale_selected_student_falls_back_to_placeholder():
    # 15-pass finding: a selectedStudent no longer on the roster must not let
    # the browser silently select the first enabled option.
    assert "state.students.some(student => student.student_id === state.selectedStudent)" in HTML


def test_gir_null_score_is_not_treated_as_zero():
    # 15-pass finding: gir.score null/absent means "no signal", never "0.00".
    assert 'gir.score === null || gir.score === undefined' in HTML


def test_recorder_setup_failure_releases_mic():
    # 15-pass finding: MediaRecorder setup crash after getUserMedia must not
    # strand a live mic track.
    assert "Voice input failed to start. You can still type." in HTML


def test_student_placeholder_and_refusals():
    assert "Choose a student…" in HTML
    assert "Choose a student before saving. Nothing was saved." in HTML
    # Empty selection renders a lens empty state instead of /api/students//lens.
    assert "if (!state.selectedStudent) {" in HTML


# --- §8.2: companion hidden, backend intact -----------------------------------

def test_voice_companion_hidden_for_day_one():
    assert '<body class="voice-hidden">' in HTML
    assert "body.voice-hidden .voice-companion" in HTML
    # The UI entry point is hidden, not deleted — probe/act wiring stays.
    assert 'id="vc-mic"' in HTML
    assert "/api/voice/act" in HTML


def test_no_copy_references_hidden_companion():
    assert "voice companion mic" not in HTML.lower()
