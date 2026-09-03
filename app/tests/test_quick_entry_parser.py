"""core/quick_entry_parser.py — pure parsing of QuickTaskEntry's
"<category>: due <when>: <title>" shorthand. No Qt/DB involved."""

from datetime import date, timedelta

from app.core.quick_entry_parser import parse_quick_entry

TODAY = date(2026, 6, 15)


def test_valid_shorthand_resolves_category_and_due_today():
    result = parse_quick_entry("work: due today: complete geneva application", TODAY)
    assert result.title == "complete geneva application"
    assert result.category == "Work"
    assert result.due_date == TODAY


def test_valid_shorthand_is_case_insensitive_on_category_and_due_keyword():
    result = parse_quick_entry("SCHOOL: DUE tomorrow: submit assignment 2", TODAY)
    assert result.title == "submit assignment 2"
    assert result.category == "School"
    assert result.due_date == TODAY + timedelta(days=1)


def test_tomorrow_resolves_relative_to_today():
    result = parse_quick_entry("personal: due tomorrow: renew passport", TODAY)
    assert result.due_date == TODAY + timedelta(days=1)


def test_yesterday_resolves_to_the_literal_past_date_unnormalized():
    """Clamping a past due date forward to today is TaskService's job
    (see core/date_service.normalize_due_date) — the parser itself just
    resolves what the shorthand literally names."""
    result = parse_quick_entry("personal: due yesterday: renew passport", TODAY)
    assert result.due_date == TODAY - timedelta(days=1)
    assert result.category == "Personal"
    assert result.title == "renew passport"


def test_invalid_category_falls_back_to_plain_title():
    text = "hobby: due today: paint the fence"
    result = parse_quick_entry(text, TODAY)
    assert result.title == text
    assert result.category is None
    assert result.due_date is None


def test_missing_due_clause_falls_back_to_plain_title():
    text = "work: complete geneva application"
    result = parse_quick_entry(text, TODAY)
    assert result.title == text
    assert result.category is None
    assert result.due_date is None


def test_unrecognized_when_falls_back_to_plain_title():
    text = "work: due next friday: complete geneva application"
    result = parse_quick_entry(text, TODAY)
    assert result.title == text
    assert result.category is None
    assert result.due_date is None


def test_plain_title_with_no_colons_is_unaffected():
    result = parse_quick_entry("buy milk", TODAY)
    assert result.title == "buy milk"
    assert result.category is None
    assert result.due_date is None


def test_surrounding_whitespace_is_trimmed():
    result = parse_quick_entry("  work : due today :  complete geneva application  ", TODAY)
    assert result.title == "complete geneva application"
    assert result.category == "Work"
    assert result.due_date == TODAY
