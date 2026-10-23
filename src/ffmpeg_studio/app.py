"""Application entry point and Qt bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from ffmpeg_studio import __version__
from ffmpeg_studio.assets import source_path
from ffmpeg_studio.core.logging import configure_logging
from ffmpeg_studio.services.settings import SettingsService
from ffmpeg_studio.ui.main_window import MainWindow


def main() -> int:
    """Start the desktop application."""
    configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("FFmpeg Studio")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("FFmpeg Studio")
    application.setWindowIcon(QIcon(str(source_path("icon.jfif"))))
    for font_file in ("NotoSansSC-VF.ttf", "msyh.ttc"):
        font_id = QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / font_file))
        if font_id >= 0:
            application.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
            break

    settings = SettingsService()
    window = MainWindow(settings)
    if "--smoke-test" in sys.argv:
        window.show()
        application.processEvents()
        assets_ready = (
            not window.windowIcon().isNull()
            and not window.brand.pixmap().isNull()
            and not window.status_logo.pixmap().isNull()
            and window.timeline.height() <= 280
            and window.maximumHeight() > 1024
        )
        window.close()
        return 0 if assets_ready else 2
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
