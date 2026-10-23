"""Application entry point and Qt bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ffmpeg_studio.core.logging import configure_logging
from ffmpeg_studio.services.settings import SettingsService
from ffmpeg_studio.ui.main_window import MainWindow


def main() -> int:
    """Start the desktop application."""
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("FFmpeg Studio")
    application.setOrganizationName("FFmpeg Studio")

    settings = SettingsService()
    window = MainWindow(settings)
    window.show()
    return application.exec()
