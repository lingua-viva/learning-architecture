"""Tests for src/education/ops_classifier.py (spec §3.2, deterministic)."""

from datetime import date

from src.education.ops_classifier import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    classify_ops_message,
    clean_text,
    extract_date,
    extract_periods,
    extract_subject_name,
    extract_time_window,
)

TODAY = date(2026, 7, 27)  # a Monday


def classify(text, **kwargs):
    kwargs.setdefault("today", TODAY)
    return classify_ops_message(text, **kwargs)


# --- North Star canonical examples ------------------------------------------

def test_absence_with_coverage_and_periods():
    msg = classify("I'm out tomorrow. Fever. Need coverage for 2nd and 4th period.")
    assert msg.category == "absence"
    assert msg.confidence == CONFIDENCE_HIGH
    assert msg.date_for == "2026-07-28"
    assert msg.periods == [2, 4]
    assert msg.wants_coverage is True


def test_coverage_request_with_time_range():
    msg = classify("Need substitute for Claudia, Grade 4, 9:00-11:30.")
    assert msg.category == "coverage_request"
    assert msg.confidence == CONFIDENCE_HIGH
    assert msg.time_window == "9:00-11:30"
    assert msg.subject == "Claudia"


def test_schedule_change_assembly():
    msg = classify("Assembly moved to 10:30.", is_ops_channel=True)
    assert msg.category == "schedule_change"
    assert msg.confidence == CONFIDENCE_HIGH
    assert msg.time_window == "10:30"


def test_student_logistics_early_pickup():
    msg = classify("Sofia has an early pickup at 1:45.")
    assert msg.category == "student_logistics"
    assert msg.confidence == CONFIDENCE_HIGH
    assert msg.subject == "Sofia"
    assert msg.time_window == "1:45"


def test_leave_early_dismissal_coverage():
    msg = classify("I need to leave 20 minutes early today. Can someone cover dismissal?")
    assert msg.category == "coverage_request"
    assert msg.date_for == "2026-07-27"


def test_facilities_projector():
    msg = classify("Projector in Room 12 is not working.")
    assert msg.category == "facilities"
    assert msg.confidence == CONFIDENCE_HIGH


def test_reminder_forms_due():
    msg = classify("Grade 3 field trip forms due.", is_ops_channel=True)
    assert msg.category == "reminder"


def test_announcement_fallback_in_ops_channel():
    msg = classify("Lunch will be served in the gym this week.", is_ops_channel=True)
    assert msg.category == "announcement"
    assert msg.confidence == CONFIDENCE_HIGH


def test_dm_chatter_is_other_low():
    msg = classify("Thanks so much!", is_dm=True)
    assert msg.category == "other"
    assert msg.confidence == CONFIDENCE_LOW
    assert msg.clarification


# --- absence vs student logistics disambiguation ----------------------------

def test_self_absence_not_student_logistics():
    msg = classify("I'm sick, won't be in.")
    assert msg.category == "absence"
    assert msg.date_for == "2026-07-27"  # sick with no date defaults to today
    assert msg.subject is None


def test_student_absent_is_logistics_not_absence():
    msg = classify("Mateo absent today, parent called.")
    assert msg.category == "student_logistics"
    assert msg.subject == "Mateo"


def test_student_logistics_without_name_asks_who():
    msg = classify("Early pickup at 1:45 today.")
    assert msg.category == "student_logistics"
    assert msg.confidence == CONFIDENCE_LOW
    assert "Who" in msg.clarification


def test_out_of_supplies_is_not_an_absence():
    # "I'm out of paper" is supply talk, not a teacher absence (hardening
    # pass 11).
    for text in (
        "I'm out of paper for the copier.",
        "I am out of glue sticks again.",
        "I'll be out of copies by Friday.",
    ):
        assert classify(text).category != "absence", text


def test_out_of_town_or_office_is_still_an_absence():
    for text, expected_date in (
        ("I'm out of town Thursday.", "2026-07-30"),
        ("I'll be out of the office tomorrow.", "2026-07-28"),
    ):
        msg = classify(text)
        assert msg.category == "absence", text
        assert msg.date_for == expected_date


# --- coverage --------------------------------------------------------------

def test_coverage_claim():
    msg = classify("I can cover that.")
    assert msg.category == "coverage_claim"
    assert msg.confidence == CONFIDENCE_HIGH


def test_coverage_request_without_details_is_low():
    msg = classify("Who can cover for me?")
    assert msg.category == "coverage_request"
    assert msg.confidence == CONFIDENCE_LOW
    assert "coverage" in msg.clarification.lower()


def test_absence_without_coverage_language():
    msg = classify("I'll be out on Friday.")
    assert msg.category == "absence"
    assert msg.date_for == "2026-07-31"
    assert msg.wants_coverage is False


# --- date parsing -----------------------------------------------------------

def test_extract_date_variants():
    assert extract_date("out tomorrow", TODAY) == "2026-07-28"
    assert extract_date("back today", TODAY) == "2026-07-27"
    assert extract_date("meeting on Wednesday", TODAY) == "2026-07-29"
    assert extract_date("due July 30", TODAY) == "2026-07-30"
    assert extract_date("due Jul 30th", TODAY) == "2026-07-30"
    assert extract_date("on 7/30", TODAY) == "2026-07-30"
    assert extract_date("on 2026-08-03", TODAY) == "2026-08-03"
    assert extract_date("no date here", TODAY) is None


def test_same_weekday_means_next_week():
    assert extract_date("on Monday", TODAY) == "2026-08-03"


def test_past_month_day_rolls_to_next_year():
    assert extract_date("on January 5", TODAY) == "2027-01-05"


def test_invalid_dates_are_ignored():
    assert extract_date("on 13/45", TODAY) is None
    assert extract_date("February 30", TODAY) is None


# --- periods and times ------------------------------------------------------

def test_extract_periods_variants():
    assert extract_periods("2nd and 4th period") == [2, 4]
    assert extract_periods("1st, 2nd and 3rd periods") == [1, 2, 3]
    assert extract_periods("period 5") == [5]
    assert extract_periods("cover 2nd period and period 2") == [2]  # dedup
    assert extract_periods("the 21st of May") == []  # not a period
    assert extract_periods("no periods") == []


def test_extract_time_window_variants():
    assert extract_time_window("9:00-11:30") == "9:00-11:30"
    assert extract_time_window("9.00 to 11.30") == "9:00-11:30"
    assert extract_time_window("moved to 10:30") == "10:30"
    assert extract_time_window("nothing") is None


# --- names and cleaning -----------------------------------------------------

def test_subject_name_skips_non_names():
    assert extract_subject_name("Sofia has an early pickup") == "Sofia"
    assert extract_subject_name("On Monday the Grade 4 trip leaves") is None
    assert extract_subject_name("I will be late") is None


def test_clean_text_strips_mentions_and_whitespace():
    assert clean_text("<@U123ABC>  hello   world ") == "hello world"


def test_empty_message_is_low_other():
    msg = classify("<@U123ABC>")
    assert msg.category == "other"
    assert msg.confidence == CONFIDENCE_LOW


# --- safety -----------------------------------------------------------------

def test_oversized_text_truncated_no_crash():
    msg = classify("I'm out tomorrow. " + "x" * 30_000)
    assert msg.category == "absence"
    assert len(msg.text_clean) <= 20_000
