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

from PySide6.QtWidgets import QApplication

from app.core import date_service
from app.core.state_engine import reconcile
from app.database.db import default_db_path, get_connection, initialize_database
from app.database.repositories.app_state_repository import AppStateRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.fixed_event_repository import FixedEventRepository
from app.database.repositories.history_repository import HistoryRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.schedule_repository import ScheduleRepository
from app.database.repositories.task_repository import TaskRepository
from app.logging_config import configure_logging
from app.notifications.notification_service import NullNotificationService
from app.services.history_service import HistoryService
from app.services.schedule_service import ScheduleService
from app.services.task_service import TaskService
from app.ui.main_window import build_main_window

logger = logging.getLogger(__name__)


def _reconcile_startup_state(task_repo, schedule_service, app_state_repo, history_service, today):
    """Steps 3-4 of the startup sequence — see core/state_engine.reconcile
    for the actual replay logic. Never persists last_known_date unless the
    whole pass completes without raising."""
    last_known_date = app_state_repo.get_last_known_date()
    schedule_map = (
        schedule_service.get_task_ids_between(last_known_date, today)
        if last_known_date is not None else {}
    )
    all_tasks = {t.id: t for t in task_repo.list_all(include_cancelled=True)}
    db_state = {"tasks": all_tasks, "schedule": schedule_map, "weekly_history": []}

    result = reconcile(last_known_date, today, db_state)

    for task in all_tasks.values():
        task_repo.update(task)
    if result.weeks_archived:
        history_service.apply_reconciliation_archives(result.weeks_archived)
        for week in result.weeks_archived:
            logger.info("Archived week %s - %s", week["week_start"], week["week_end"])
    if result.tasks_marked_missed:
        logger.info(
            "Reconciliation marked %d task(s) missed: %s",
            len(result.tasks_marked_missed), result.tasks_marked_missed,
        )

    app_state_repo.set_last_known_date(today)
    return result


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

    # Real WindowsNotificationService lands in Phase 7 — the go/no-go spike
    # passed (scripts/notification_spike.py), but wiring it into the
    # services layer is separable from the vertical slice.
    notification_service = NullNotificationService()

    task_service = TaskService(task_repo, notification_service)
    schedule_service = ScheduleService(task_repo, schedule_repo, fixed_event_repo)
    history_service = HistoryService(history_repo)

    today = date_service.today()
    _reconcile_startup_state(task_repo, schedule_service, app_state_repo, history_service, today)

    this_week_start = date_service.week_start(today)
    if not schedule_service.week_is_planned(this_week_start):
        logger.info("Week of %s has not been planned yet.", this_week_start)

    app = QApplication(sys.argv)
    window = build_main_window(task_service, schedule_service, project_repo, category_repo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
