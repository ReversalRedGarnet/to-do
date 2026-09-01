"""Live smart auto-fill: parses a task title for day/date, effort, and
urgency/importance hints, plus a project name match. Pure and Qt/DB-free
(mirrors core/scheduling_engine.py's "no direct datetime.now() calls
inside core logic" rule — callers always pass `today` explicitly), so the
UI layer (ui/task_editor.py) is the only place that knows about widgets,
debouncing, or the "don't clobber a manual edit" guardrail.

Deadline convention: the deadline is the day *before* whatever day/date
the title mentions (e.g. "team sync sat" -> deadline Friday — the prep
work is due the day before the event). Two intentional exceptions to a
literal reading of that rule, chosen to avoid a nonsensical result:
  - "today" is not treated as a day/date mention at all — day-before
    would be a past date (yesterday), which is never a useful deadline.
    The same exemption applies to an explicit date that resolves to
    today (e.g. typing "9/1" when today is September 1st) — it is not
    only the literal word "today" that must dodge this.
  - "tomorrow" is applied literally: deadline = today (the day before
    tomorrow). This can read as counter-intuitive ("call mom tomorrow"
    sets today as the deadline, not tomorrow) but keeps the convention
    consistent rather than special-casing it.
A bare weekday ("sat") always resolves to its *next* occurrence, 1-7 days
out — never today — again to keep day-before from landing in the past.
"next <weekday>" resolves to 7 days after that (the following week's
occurrence), so "next sat" and "sat" are never the same date.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Iterable, Optional, Tuple

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
_WEEKDAY_PATTERN = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))

_LOW_EFFORT_WORDS = {"quick", "small", "tiny", "short", "brief"}
_HIGH_EFFORT_WORDS = {"big", "huge", "major", "large"}
_URGENCY_WORDS = {"urgent", "asap"}
_IMPORTANCE_WORDS = {"important"}

# Effort is still the existing 1-5 scale (see config/settings.py) — these
# are just the extremes a "quick"/"huge" hint maps onto, not a new scale.
LOW_EFFORT = 1
HIGH_EFFORT = 5
BUMPED_LEVEL = 5  # what "urgent"/"asap"/"important" bump urgency/importance to

_PROJECT_FUZZY_THRESHOLD = 0.75


@dataclass
class TitleHints:
    deadline: Optional[date] = None
    effort: Optional[int] = None
    urgency: Optional[int] = None
    importance: Optional[int] = None
    project_id: Optional[int] = None


def _mentioned_day(title: str, today: date) -> Optional[date]:
    text = title.lower()

    explicit = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if explicit:
        month, day = int(explicit.group(1)), int(explicit.group(2))
        year_group = explicit.group(3)
        year = today.year
        if year_group:
            year = int(year_group)
            if year < 100:
                year += 2000
        try:
            candidate = date(year, month, day)
        except ValueError:
            candidate = None
        if candidate is not None:
            if year_group is None and candidate < today:
                candidate = date(year + 1, month, day)
            if candidate != today:
                return candidate
            # Same exemption as the literal word "today": a literal
            # day-before reading would be yesterday, a past date, so an
            # explicit date that happens to resolve to today is not
            # treated as a deadline trigger — fall through to check for
            # any other day/date phrasing elsewhere in the title.

    in_days = re.search(r"\bin\s+(\d+)\s+days?\b", text)
    if in_days:
        return today + timedelta(days=int(in_days.group(1)))

    next_weekday = re.search(rf"\bnext\s+({_WEEKDAY_PATTERN})\b", text)
    if next_weekday:
        target = _WEEKDAYS[next_weekday.group(1)]
        days_ahead = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead + 7)

    if re.search(r"\btomorrow\b", text):
        return today + timedelta(days=1)

    bare_weekday = re.search(rf"\b({_WEEKDAY_PATTERN})\b", text)
    if bare_weekday:
        target = _WEEKDAYS[bare_weekday.group(1)]
        days_ahead = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)

    return None


def infer_deadline(title: str, today: date) -> Optional[date]:
    mentioned = _mentioned_day(title, today)
    return mentioned - timedelta(days=1) if mentioned is not None else None


def _has_any_word(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def infer_effort(title: str) -> Optional[int]:
    text = title.lower()
    if re.search(r"\b\d+\s*min(ute)?s?\b", text) or _has_any_word(text, _LOW_EFFORT_WORDS):
        return LOW_EFFORT
    if _has_any_word(text, _HIGH_EFFORT_WORDS):
        return HIGH_EFFORT
    return None


def infer_urgency(title: str) -> Optional[int]:
    return BUMPED_LEVEL if _has_any_word(title.lower(), _URGENCY_WORDS) else None


def infer_importance(title: str) -> Optional[int]:
    return BUMPED_LEVEL if _has_any_word(title.lower(), _IMPORTANCE_WORDS) else None


def infer_project(title: str, projects: Iterable[Tuple[int, str]]) -> Optional[int]:
    """`projects` is (id, name) pairs — a whole-word/phrase substring
    match wins outright; otherwise a per-word fuzzy match (typo
    tolerance) against project names of at least 4 characters."""
    text = title.lower()
    projects = list(projects)

    for project_id, name in projects:
        name_lower = name.lower().strip()
        if name_lower and re.search(rf"\b{re.escape(name_lower)}\b", text):
            return project_id

    words = re.findall(r"[a-z0-9']+", text)
    best_id, best_score = None, 0.0
    for project_id, name in projects:
        name_lower = name.lower().strip()
        if len(name_lower) < 4:
            continue
        for word in words:
            score = SequenceMatcher(None, name_lower, word).ratio()
            if score > best_score:
                best_score, best_id = score, project_id
    return best_id if best_score >= _PROJECT_FUZZY_THRESHOLD else None


def parse_title_hints(title: str, today: date, projects: Iterable[Tuple[int, str]] = ()) -> TitleHints:
    return TitleHints(
        deadline=infer_deadline(title, today),
        effort=infer_effort(title),
        urgency=infer_urgency(title),
        importance=infer_importance(title),
        project_id=infer_project(title, projects),
    )
