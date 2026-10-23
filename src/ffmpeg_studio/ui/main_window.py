"""The minimal application shell used while MVP pages are built."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QStatusBar, QTabWidget, QVBoxLayout, QWidget

from ffmpeg_studio.services.settings import SettingsService


class MainWindow(QMainWindow):
    """Top-level window and navigation placeholder for MVP workflows."""

    def __init__(self, settings_service: SettingsService) -> None:
        super().__init__()
        self._settings_service = settings_service
        self.setWindowTitle("FFmpeg Studio")
        self.resize(1200, 760)
        self.setMinimumSize(960, 640)
        self.setCentralWidget(self._build_central_widget())
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("正在检查 FFmpeg 环境…")

    def _build_central_widget(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 20, 28, 24)

        title = QLabel("FFmpeg Studio")
        title.setObjectName("applicationTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)

        tabs = QTabWidget(container)
        for page_name in ("概览", "转码", "裁剪", "音频", "队列", "设置"):
            page = QWidget(tabs)
            page_layout = QVBoxLayout(page)
            placeholder = QLabel(f"{page_name}功能将在后续任务中实现")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page_layout.addWidget(placeholder)
            tabs.addTab(page, page_name)
        layout.addWidget(tabs)
        return container
