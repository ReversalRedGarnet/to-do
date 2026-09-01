"""core/title_parser.py — pure title-hint parsing behind the task editor's
live smart auto-fill. No Qt/DB involved; see test_task_editor_auto_fill.py
for the dialog-level wiring (debounce, manual-edit guardrail, markers)."""

from datetime import date

from app.core.title_parser import (
    HIGH_EFFORT, LOW_EFFORT, infer_deadline, infer_effort, infer_importance,
    infer_project, infer_urgency, parse_title_hints,
)

MONDAY = date(2026, 6, 15)  # 6/20 = Saturday, 6/21 = Sunday


# --- Deadline: day-before-the-mentioned-day convention ---

def test_bare_weekday_sets_deadline_to_the_day_before_its_next_occurrence():
    assert infer_deadline("team sync sat", MONDAY) == date(2026, 6, 19)  # Fri, day before Sat 6/20


def test_full_weekday_name_behaves_the_same_as_the_abbreviation():
    assert infer_deadline("team sync saturday", MONDAY) == infer_deadline("team sync sat", MONDAY)


def test_bare_weekday_matching_today_resolves_to_next_week_not_today():
    """Prevents a deadline of "yesterday": if today is itself the named
    weekday, the mention resolves to next week's occurrence (Mon 6/22),
    not today — deadline is the day before that, Sun 6/21."""
    assert infer_deadline("standup mon", MONDAY) == date(2026, 6, 21)


def test_next_weekday_is_a_full_week_after_the_bare_form():
    bare = infer_deadline("gym sat", MONDAY)
    nxt = infer_deadline("gym next sat", MONDAY)
    assert (nxt - bare).days == 7


def test_tomorrow_sets_deadline_to_today():
    """Applying the day-before convention literally: deadline = the day
    before tomorrow = today."""
    assert infer_deadline("call mom tomorrow", MONDAY) == MONDAY


def test_today_is_not_treated_as_a_deadline_trigger():
    """A literal day-before reading of "today" would be yesterday — a
    past date — so "today" deliberately triggers no auto-fill at all."""
    assert infer_deadline("finish this today", MONDAY) is None


def test_in_n_days_sets_deadline_to_the_day_before_that_offset():
    assert infer_deadline("ship in 3 days", MONDAY) == date(2026, 6, 17)


def test_explicit_date_sets_deadline_to_the_day_before_it():
    assert infer_deadline("flight 9/5", date(2026, 1, 1)) == date(2026, 9, 4)


def test_explicit_past_date_this_year_rolls_to_next_year():
    assert infer_deadline("flight 9/5", date(2026, 10, 1)) == date(2027, 9, 4)


def test_explicit_date_equal_to_today_is_also_not_treated_as_a_deadline_trigger():
    """The "today" exemption above must not be special-cased to the
    literal word — typing today's own date explicitly (here 6/15, and
    today is MONDAY = 2026-06-15) is exactly the same nonsensical
    day-before-is-yesterday case."""
    assert infer_deadline("flight 6/15", MONDAY) is None


def test_explicit_date_equal_to_today_still_falls_through_to_other_phrasing():
    """Exempting the explicit-today match must not swallow a genuine,
    different day mention elsewhere in the same title."""
    assert infer_deadline("flight 6/15 but really sat", MONDAY) == date(2026, 6, 19)


def test_no_day_mention_yields_no_deadline():
    assert infer_deadline("write the report", MONDAY) is None


# --- Effort hints ---

def test_quick_small_and_minutes_phrasing_all_infer_low_effort():
    assert infer_effort("quick call") == LOW_EFFORT
    assert infer_effort("small fix") == LOW_EFFORT
    assert infer_effort("5 min errand") == LOW_EFFORT
    assert infer_effort("10 minutes of admin") == LOW_EFFORT


def test_big_huge_major_all_infer_high_effort():
    assert infer_effort("big presentation") == HIGH_EFFORT
    assert infer_effort("huge refactor") == HIGH_EFFORT
    assert infer_effort("major release") == HIGH_EFFORT


def test_word_boundary_prevents_a_false_positive_substring_match():
    assert infer_effort("bigger picture planning") is None  # "big" must not match inside "bigger"


def test_no_effort_hint_yields_none():
    assert infer_effort("write the report") is None


# --- Urgency / importance hints ---

def test_urgent_and_asap_bump_urgency_only():
    hints = parse_title_hints("urgent: call the bank", MONDAY)
    assert hints.urgency == 5
    assert hints.importance is None

    hints = parse_title_hints("reply asap", MONDAY)
    assert hints.urgency == 5


def test_important_bumps_importance_only():
    hints = parse_title_hints("important client review", MONDAY)
    assert hints.importance == 5
    assert hints.urgency is None


def test_no_urgency_or_importance_hint_yields_none():
    assert infer_urgency("write the report") is None
    assert infer_importance("write the report") is None


# --- Project auto-match ---

def test_title_containing_the_project_name_matches_it():
    assert infer_project("fix launch page bug", [(1, "Launch")]) == 1


def test_title_not_matching_any_project_yields_none():
    assert infer_project("fix launch page bug", [(1, "Redesign")]) is None


def test_close_typo_of_a_project_name_still_matches():
    assert infer_project("fix lanuch page bug", [(1, "Launch")]) == 1


def test_short_project_names_are_not_fuzzy_matched_to_avoid_false_positives():
    # "Q3" is under the 4-char fuzzy-match floor, so only an exact/whole-
    # word mention of it should match, never a loose fuzzy guess.
    assert infer_project("some unrelated task", [(1, "Q3")]) is None


# --- Combined parse ---

def test_parse_title_hints_combines_every_category_independently():
    hints = parse_title_hints("quick urgent launch call sat", MONDAY, [(1, "Launch")])
    assert hints.deadline == date(2026, 6, 19)
    assert hints.effort == LOW_EFFORT
    assert hints.urgency == 5
    assert hints.importance is None
    assert hints.project_id == 1
