"""Application logging configuration."""

from __future__ import annotations

import logging
from pathlib import Path

APP_LOGGER_NAME = "ffmpeg_studio"


def configure_logging(log_directory: Path | None = None) -> logging.Logger:
    """Configure the application logger once and return it.

    A caller may provide a log directory; otherwise only console logging is enabled.
    """
    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_directory is not None:
        log_directory.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_directory / "ffmpeg-studio.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
