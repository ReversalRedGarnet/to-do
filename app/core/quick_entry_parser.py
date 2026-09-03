"""Parses QuickTaskEntry's colon-delimited shorthand:

    <category>: due <when>: <title>

e.g. "work: due today: complete geneva application". Pure and Qt/DB-free
(mirrors core/title_parser.py's separation) so the UI layer
(ui/task_entry.py) is the only place that knows about widgets.

Anything that doesn't cleanly match the shape above — an unrecognized
category, a missing/malformed "due <when>" clause, an unrecognized
`<when>` — falls back to treating the whole original string as a plain
title, with no category or due date inferred. Never raises.

Due-date resolution only produces the date the shorthand names; clamping
a past date (e.g. "due yesterday") forward to today is deliberately NOT
done here — that's a general task-creation concern handled once in
`services.task_service.TaskService.create_task` via
`core.date_service.normalize_due_date`, not duplicated in every entry
path that can produce a due date.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from app.config.settings import DEFAULT_CATEGORIES

_CANONICAL_CATEGORY = {name.lower(): name for name in DEFAULT_CATEGORIES}

_DUE_PREFIX = "due "

_RELATIVE_DAYS = {
    "today": 0,
    "tomorrow": 1,
    "yesterday": -1,
}


@dataclass
class QuickEntryResult:
    title: str
    category: Optional[str] = None
    due_date: Optional[date] = None


def _resolve_when(when: str, today: date) -> Optional[date]:
    offset = _RELATIVE_DAYS.get(when)
    return today + timedelta(days=offset) if offset is not None else None


def parse_quick_entry(text: str, today: date) -> QuickEntryResult:
    fallback = QuickEntryResult(title=text.strip())

    parts = text.split(":", 2)
    if len(parts) != 3:
        return fallback

    category_part, due_part, title_part = (p.strip() for p in parts)
    category = _CANONICAL_CATEGORY.get(category_part.lower())
    title_part = title_part.strip()
    due_part_lower = due_part.lower()

    if category is None or not title_part or not due_part_lower.startswith(_DUE_PREFIX):
        return fallback

    when = due_part_lower[len(_DUE_PREFIX):].strip()
    due_date = _resolve_when(when, today)
    if due_date is None:
        return fallback

    return QuickEntryResult(title=title_part, category=category, due_date=due_date)
