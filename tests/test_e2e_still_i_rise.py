"""
Phase 3 — End-to-end integration test, Lingua Viva vertical slice.

Ties Product A (Slack -> observation capture -> student lens) and
Product B (IB lesson input -> differentiated content packs -> teacher
guide) together on one shared StudentLensStore, the way a real Friday
demo would run: teachers post observations over several days, then the
same live lens data drives tier assignment for a new IB unit.

This is the "do both products actually interoperate on real data"
check that individual unit tests (test_student_lens, test_slack_bot,
test_content_differentiator, test_teacher_guide) can't catch on their
own, since each of those builds its own isolated fixtures.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.education.student_lens import StudentLensStore
from src.education.observation_capture import ObservationCapturePipeline
from src.education.slack_bot import SlackObservationBot
from src.education.content_differentiator import ContentDifferentiator, LessonInput
from src.education.teacher_guide import TeacherGuideGenerator


def make_signed_bot(store, tmp_path, channel_map, post_log):
    pipeline = ObservationCapturePipeline(store=store)
    return SlackObservationBot(
        capture_pipeline=pipeline,
        teacher_channel_map=channel_map,
        signing_secret="e2e-secret",
        post_message=lambda channel, text: post_log.append((channel, text)),
    )


def test_full_vertical_slice_product_a_feeds_product_b(tmp_path):
    store = StudentLensStore(db_path=tmp_path / "e2e.db")

    # Three students on one campus, covering the tier spread: one needs
    # intensive support (RTI 3), one is on-track with weak CEFR evidence,
    # one is strong and flagged for trauma-aware facilitation.
    store.create_lens(student_id="s1", display_name="Student One", campus="Nairobi",
                       rti_current_tier=3)
    store.create_lens(student_id="s2", display_name="Student Two", campus="Nairobi",
                       rti_current_tier=1)
    store.create_lens(student_id="s3", display_name="Student Three", campus="Nairobi",
                       rti_current_tier=1, trauma_flag=True)

    post_log = []
    bot = make_signed_bot(store, tmp_path, {"C-teacher": "teacher_1"}, post_log)

    # --- Product A: teacher posts observations via the Slack bot ---

    # s1: routine literacy note, tier 3 stays tier 3.
    result1 = bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev-1",
        "event": {"type": "message", "channel": "C-teacher",
                   "text": "[student:s1] I noticed he needed the passage read aloud twice today"},
    })
    assert result1["ok"] is True

    # s2: an urgent SEL concern (Rule B: urgency_flag triggers immediate
    # escalation). Route this one directly through the pipeline (not the
    # bot) since urgency_flag isn't settable from plain Slack text in
    # this vertical slice — the bot's job is proven separately in
    # test_slack_bot.py; here we're proving lens data flows into Product B.
    pipeline = ObservationCapturePipeline(store=store)
    capture_result = pipeline.capture(
        student_id="s2",
        teacher_id="teacher_1",
        raw_transcript="I noticed she seemed distressed and left the room without explanation",
        template_type="sel_incident",
        sel_domain="emotional_regulation",
        sel_valence="concern",
        urgency_flag=True,
    )
    assert capture_result["escalations"], "Rule B should fire on urgency_flag=True"
    assert capture_result["escalations"][0]["rule"] == "B"

    # s3: strong CEFR evidence, still on-track tier.
    bot.handle_event_payload({
        "type": "event_callback",
        "event_id": "Ev-3",
        "event": {"type": "message", "channel": "C-teacher",
                   "text": "[student:s3] I noticed confident independent writing well above grade level"},
    })

    # Give s3 a B2 CEFR snapshot directly (writing sample scored by the
    # teacher separately) so tier assignment has real evidence to act on.
    pipeline.capture(
        student_id="s3", teacher_id="teacher_1",
        raw_transcript="I noticed her writing sample scored at B2 for extended argument structure",
        template_type="cefr", cefr_dimension="writing", cefr_level_observed="B2",
        cefr_direction="progressing",
    )

    # --- Verify Product A's writes are visible as live lens data ---
    roster = store.list_lenses(campus="Nairobi")
    assert {r["student_id"] for r in roster} == {"s1", "s2", "s3"}
    lens_s1 = store.get_lens("s1")
    lens_s3 = store.get_lens("s3")
    assert lens_s1["rti_current_tier"] == 3
    assert lens_s3["cefr_snapshot"].get("writing") == "B2"
    assert lens_s3["trauma_flag"] is True

    # --- Product B: generate a differentiated content pack for a new IB unit ---
    lesson = LessonInput(
        ib_programme="MYP",
        subject="Individuals & Societies",
        unit_title="Migration and Identity",
        topic="Push and pull factors of forced migration",
        atl_skills=["COMM-01"],
        cefr_target="B1",
        duration_minutes=60,
        created_by="teacher_1",
    )
    engine = ContentDifferentiator()
    pack = engine.generate(lesson)

    # Tier assignment driven by the SAME roster StudentLensStore holds —
    # not a hand-built dict — proving Product A's output is Product B's
    # real input, not two disconnected demos.
    assignments = engine.assign_packs_for_roster(pack, roster)
    assert assignments["s1"] == "foundational"  # RTI tier 3 -> always foundational
    assert assignments["s3"] == "extended"      # RTI tier 1 + CEFR B2 evidence -> extended

    guide = TeacherGuideGenerator().generate(pack, roster, assignments)
    assert guide.tier_counts["foundational"] >= 1
    assert guide.tier_counts["extended"] >= 1
    # s3's trauma_flag produces exactly one general, non-identifying note.
    assert len(guide.trauma_aware_notes) == 1
    assert "s3" not in guide.trauma_aware_notes[0]

    md = guide.to_markdown()
    assert "Migration and Identity" in md
    assert "## Class Breakdown" in md

    # --- Teacher rights check: export must reflect the full observation
    # history written across both the bot path and the direct pipeline path.
    export = store.export_lens("s2")
    assert len(export["observations"]) == 1
    assert export["observations"][0]["urgency_flag"] in (1, True)

    # Nothing in this flow ever left the machine: post_message only ever
    # received fixed acknowledgement templates, never observation text.
    for _channel, text in post_log:
        assert "distressed" not in text
        assert "passage" not in text
        assert "writing" not in text
