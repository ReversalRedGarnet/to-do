"""
Entry point for the Personal Adaptive Weekly Task Planner.

Startup sequence (see ARCHITECTURE.md):
    1. Load database
    2. Detect current date
    3. Reconcile date rollover (core.date_service / core.state_engine)
    4. Reconcile missed tasks
    5. Verify current week's schedule exists
    6. Update today's board
    7. Initialize notification service
    8. Display dashboard
"""

import logging
import sys
from datetime import timedelta

from PySide6.QtWidgets import QApplication

from app.core import date_service
from app.core.priority_engine import calculate_priority_score
from app.database.db import default_db_path, get_connection, initialize_database
from app.database.repositories.app_state_repository import AppStateRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.history_repository import HistoryRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.settings_repository import SettingsRepository
from app.database.repositories.task_repository import TaskRepository
from app.logging_config import configure_logging
from app.notifications.notification_service import WindowsNotificationService
from app.services.history_service import HistoryService
from app.services.reconciliation_service import ReconciliationService
from app.services.schedule_service import ScheduleService
from app.services.task_service import TaskService
from app.ui.main_window import build_main_window

logger = logging.getLogger(__name__)

# Weekly planning reminder fires from this weekday onward (Monday=0..Sunday=6)
# if the coming week still isn't planned — Sunday is the spec's conventional
# planning day (§20, §46), not a hard restriction.
_PLANNING_REMINDER_WEEKDAY = 6


def _send_startup_notifications(
    notification_service, task_repo, schedule_service,
    app_state_repo, settings_repo, result, today,
) -> None:
    """Startup gets exactly one notification batch per day — guarded by
    last_notified_date so re-launching the app the same day, or the
    mid-session rollover timer catching up later, can't double-fire.
    notify_day_rollover is deliberately NOT sent here — it's reserved for
    the mid-session timer path (see ui/main_window.py); firing both after
    a multi-day gap would be exactly the notification spam spec §31
    warns against."""
    if app_state_repo.get_last_notified_date() == today:
        return

    if result.tasks_marked_missed:
        missed_tasks = [
            t for t in task_repo.list_by_ids(result.tasks_marked_missed)
        ]
        notification_service.notify_missed_tasks(missed_tasks)

    settings = settings_repo.get()
    this_week_start = date_service.week_start(today)
    next_week_start = this_week_start + timedelta(days=7)
    if (
        settings.sunday_reminder_enabled
        and today.weekday() >= _PLANNING_REMINDER_WEEKDAY
        and not schedule_service.week_is_planned(next_week_start)
    ):
        notification_service.notify_weekly_plan_required()

    for event in schedule_service.get_fixed_events_between(today, today):
        notification_service.notify_event(event)

    todays_entries = schedule_service.get_week(this_week_start).get(today, [])
    todays_tasks = [
        t for entry in todays_entries
        if (t := task_repo.get_by_id(entry.task_id)) is not None and t.status.value not in ("completed", "cancelled")
    ]
    if todays_tasks:
        top_task = max(todays_tasks, key=lambda t: calculate_priority_score(t, today))
        notification_service.notify_task(top_task)

    app_state_repo.set_last_notified_date(today)


def main() -> int:
    db_path = default_db_path()
    configure_logging(db_path.parent)
    logger.info("Starting Personal Adaptive Weekly Task Planner")

    initialize_database(db_path)
    conn = get_connection(db_path)

    task_repo = TaskRepository(conn)
    schedule_repo = ScheduleRepository(conn)
    fixed_event_repo = FixedEventRepository(conn)
    project_repo = ProjectRepository(conn)
    category_repo = CategoryRepository(conn)
    app_state_repo = AppStateRepository(conn)
    history_repo = HistoryRepository(conn)
    settings_repo = SettingsRepository(conn)

    notification_service = WindowsNotificationService(settings_repo)

    task_service = TaskService(task_repo, notification_service)
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    history_service = HistoryService(history_repo)
    reconciliation_service = ReconciliationService(
        task_repo, schedule_service, app_state_repo, history_service
    )

    today = date_service.today()
    result = reconciliation_service.run(today)
    if result.weeks_archived:
        for week in result.weeks_archived:
            logger.info("Archived week %s - %s", week["week_start"], week["week_end"])
    if result.tasks_marked_missed:
        logger.info(
            "Reconciliation marked %d task(s) missed: %s",
            len(result.tasks_marked_missed), result.tasks_marked_missed,
        )

    this_week_start = date_service.week_start(today)
    if not schedule_service.week_is_planned(this_week_start):
        logger.info("Week of %s has not been planned yet.", this_week_start)

    _send_startup_notifications(
        notification_service, task_repo, schedule_service,
        app_state_repo, settings_repo, result, today,
    )

    app = QApplication(sys.argv)
    window = build_main_window(
        task_service, schedule_service, project_repo, category_repo,
        reconciliation_service=reconciliation_service,
        notification_service=notification_service,
        app_state_repository=app_state_repo,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
