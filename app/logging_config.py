"""
Application logging setup (spec §53). Debugging aid only — never a
user-facing history/analytics feature.
"""

import logging
from pathlib import Path

from app.config.settings import APP_NAME


def configure_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(log_dir / f"{APP_NAME.lower()}.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
