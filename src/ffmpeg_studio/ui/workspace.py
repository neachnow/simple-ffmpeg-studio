"""FFmpeg dashboard with persistent source and processing panels."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_studio.core.ffmpeg import (
    FfmpegError,
    find_executable,
    format_command,
    inspect_executable,
)
from ffmpeg_studio.core.planner import PlannedJob, plan_jobs
from ffmpeg_studio.core.probe import MediaInfo, probe_media
from ffmpeg_studio.core.worker import JobWorker
from ffmpeg_studio.services.settings import AppSettings, SettingsService


class ProbeWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, executable: Path, source: Path) -> None:
        super().__init__()
        self.executable = executable
        self.source = source

    def run(self) -> None:
        try:
            self.completed.emit(probe_media(self.executable, self.source))
        except (FfmpegError, ValueError) as error:
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    """Each top tab changes settings; source and status stay visible."""

    def __init__(self, settings_service: SettingsService) -> None:
        super().__init__()
        self._settings_service = settings_service
        self._settings = settings_service.load()
        self._media: MediaInfo | None = None
        self._probe_worker: ProbeWorker | None = None
        self._worker: JobWorker | None = None
        self._jobs: list[PlannedJob] = []
        self._states: list[str] = []
        self._active_index: int | None = None
        self._reserved: set[Path] = set()
        self.setWindowTitle("FFmpeg Studio")
        self.resize(1180, 780)
        self.setMinimumSize(900, 640)
        self.setAcceptDrops(True)
        self.setStatusBar(QStatusBar(self))
        self.setCentralWidget(self._build_ui())
        self._apply_style()
        self._check_environment()

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)
        return card, layout

    def _build_ui(self) -> QWidget:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(20)
        self.brand = QLabel()
        self.brand.setObjectName("brand")
        self._banner = QPixmap(
            str(Path(__file__).resolve().parents[3] / "source" / "banner.jfif")
        )
        if self._banner.isNull():
            self.brand.setText("FFmpeg Studio   /   本地媒体工作台")
        else:
            self.brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._scale_banner(1108)
        layout.addWidget(self.brand)
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        for title in (
            "概览 / Overview", "转码 / Transcode", "视频分割 / Split Video",
            "提取音频 / Extract Audio", "设置 / Settings",
        ):
            self.tabs.addTab(title)
        layout.addWidget(self.tabs)
        columns = QHBoxLayout()
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(18)
        left.addWidget(self._source_card())
        self.pages = QStackedWidget()
        for page in (self._overview_page(), self._transcode_page(), self._split_page(),
                     self._audio_page(), self._settings_page()):
            self.pages.addWidget(page)
        left.addWidget(self.pages, 1)
        columns.addLayout(left, 7)
        columns.addWidget(self._status_card(), 4)
        layout.addLayout(columns, 1)
        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)
        return root

    def _source_card(self) -> QFrame:
        card, layout = self._card("源视频")
        row = QHBoxLayout()
        self.source_path = QLineEdit()
        self.source_path.setPlaceholderText("拖入视频，或选择本地文件")
        self.source_path.setReadOnly(True)
        choose = QPushButton("选择视频")
        choose.clicked.connect(self._choose_source)
        row.addWidget(self.source_path, 1)
        row.addWidget(choose)
        layout.addLayout(row)
        self.source_info = QLabel("尚未选择视频")
        self.source_info.setWordWrap(True)
        self.source_info.setObjectName("muted")
        layout.addWidget(self.source_info)
        return card

    def _form_page(self, title: str, description: str) -> tuple[QFrame, QVBoxLayout, QFormLayout]:
        page, layout = self._card(title)
        note = QLabel(description)
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        form = QFormLayout()
        form.setSpacing(14)
        layout.addLayout(form)
        return page, layout, form

    def _overview_page(self) -> QFrame:
        page, layout, _ = self._form_page(
            "开始处理", "选择源视频后，在上方切换功能。参数位于左侧，处理进度与日志显示在右侧。"
        )
        self.environment_label = QLabel("正在检测 FFmpeg 环境…")
        self.environment_label.setWordWrap(True)
        self.environment_label.setObjectName("muted")
        layout.addWidget(self.environment_label)
        layout.addStretch()
        return page

    def _transcode_page(self) -> QFrame:
        page, layout, form = self._form_page(
            "视频转码", "输出 MP4（H.264 / AAC），通过预设调整画质。"
        )
        self.quality = QComboBox()
        for label, crf in (("高质量 · CRF 18", 18), ("平衡 · CRF 23", 23),
                           ("小体积 · CRF 28", 28)):
            self.quality.addItem(label, crf)
        self.quality.setCurrentIndex(1)
        form.addRow("画质预设", self.quality)
        button = QPushButton("添加转码任务")
        button.setObjectName("primary")
        button.clicked.connect(lambda: self._add_jobs("transcode"))
        layout.addWidget(button)
        layout.addStretch()
        return page

    @staticmethod
    def _duration_controls(form: QFormLayout) -> tuple[QComboBox, QSpinBox]:
        mode = QComboBox()
        mode.addItem("按原时长（完整输出）", False)
        mode.addItem("按每段时长分割", True)
        seconds = QSpinBox()
        seconds.setRange(1, 86400)
        seconds.setValue(60)
        seconds.setSuffix(" 秒 / 段")
        seconds.setEnabled(False)
        mode.currentIndexChanged.connect(lambda: seconds.setEnabled(bool(mode.currentData())))
        form.addRow("处理范围", mode)
        form.addRow("每段时长", seconds)
        return mode, seconds

    def _split_page(self) -> QFrame:
        page, layout, form = self._form_page(
            "视频分割", "按固定秒数生成多个 MP4，或生成一段与原视频等长的 MP4。"
        )
        self.split_mode, self.split_seconds = self._duration_controls(form)
        button = QPushButton("添加视频分割任务")
        button.setObjectName("primary")
        button.clicked.connect(lambda: self._add_jobs("split"))
        layout.addWidget(button)
        layout.addStretch()
        return page

    def _audio_page(self) -> QFrame:
        page, layout, form = self._form_page(
            "提取音频", "导出第一条音轨，可选择完整音频或按时长分段。"
        )
        self.audio_mode, self.audio_seconds = self._duration_controls(form)
        self.audio_format = QComboBox()
        for name in ("MP3", "AAC", "WAV", "FLAC"):
            self.audio_format.addItem(name, name.lower())
        form.addRow("输出格式", self.audio_format)
        button = QPushButton("添加音频提取任务")
        button.setObjectName("primary")
        button.clicked.connect(lambda: self._add_jobs("audio"))
        layout.addWidget(button)
        layout.addStretch()
        return page

    def _settings_page(self) -> QFrame:
        page, layout, form = self._form_page(
            "设置", "可指定 FFmpeg 文件路径；留空时查找项目 source/ffmpeg/bin 或系统 PATH。"
        )
        self.ffmpeg_input = QLineEdit(self._settings.ffmpeg_path)
        self.ffprobe_input = QLineEdit(self._settings.ffprobe_path)
        self.output_input = QLineEdit(self._settings.default_output_directory)
        self.output_input.setPlaceholderText("留空：源视频旁的 FFmpeg Studio Output")
        form.addRow("ffmpeg.exe", self._path_picker(self.ffmpeg_input, directory=False))
        form.addRow("ffprobe.exe", self._path_picker(self.ffprobe_input, directory=False))
        form.addRow("输出目录", self._path_picker(self.output_input, directory=True))
        button = QPushButton("保存并检测")
        button.setObjectName("primary")
        button.clicked.connect(self._save_settings)
        layout.addWidget(button)
        layout.addStretch()
        return page

    def _path_picker(self, field: QLineEdit, *, directory: bool) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field, 1)
        browse = QPushButton("浏览…")

        def choose() -> None:
            if directory:
                path = QFileDialog.getExistingDirectory(self, "选择输出目录", field.text())
            else:
                path, _ = QFileDialog.getOpenFileName(
                    self, "选择 FFmpeg 可执行文件", field.text(), "可执行文件 (*.exe)"
                )
            if path:
                field.setText(path)

        browse.clicked.connect(choose)
        row.addWidget(browse)
        return container

    def _status_card(self) -> QFrame:
        card, layout = self._card("处理状态")
        self.state_label = QLabel("暂无任务")
        self.state_label.setObjectName("muted")
        layout.addWidget(self.state_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        start = QPushButton("开始队列")
        start.setObjectName("primary")
        start.clicked.connect(self._start_next)
        cancel = QPushButton("取消当前")
        cancel.clicked.connect(self._cancel_current)
        actions.addWidget(start)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        self.queue = QListWidget()
        self.queue.setMinimumHeight(150)
        layout.addWidget(self.queue, 2)
        layout.addWidget(QLabel("命令预览"))
        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setMaximumHeight(100)
        layout.addWidget(self.command_preview)
        layout.addWidget(QLabel("执行日志"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 2)
        return card

    def _candidate(self, name: str, preferred: str) -> Path | None:
        if preferred:
            return find_executable(preferred, name)
        bundled = Path(__file__).resolve().parents[3] / "source" / "ffmpeg" / "bin" / f"{name}.exe"
        return bundled if bundled.is_file() else find_executable(None, name)

    def _check_environment(self) -> None:
        ffmpeg = self._candidate("ffmpeg", self._settings.ffmpeg_path)
        ffprobe = self._candidate("ffprobe", self._settings.ffprobe_path)
        try:
            if ffmpeg is None or ffprobe is None:
                raise FfmpegError("FFmpeg 或 FFprobe 未找到，请在设置页指定路径")
            info = inspect_executable(ffmpeg)
            inspect_executable(ffprobe)
            self.environment_label.setText(f"已就绪 · {info.version}\n{ffmpeg}")
            self.statusBar().showMessage("FFmpeg 环境已就绪")
        except FfmpegError as error:
            self.environment_label.setText(str(error))
            self.statusBar().showMessage("请检查 FFmpeg 设置")

    def _save_settings(self) -> None:
        self._settings = AppSettings(
            ffmpeg_path=self.ffmpeg_input.text().strip(),
            ffprobe_path=self.ffprobe_input.text().strip(),
            default_output_directory=self.output_input.text().strip(),
            max_concurrent_jobs=self._settings.max_concurrent_jobs,
        )
        self._settings_service.save(self._settings)
        self._check_environment()

    def _choose_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频", "", "媒体文件 (*.mp4 *.mkv *.mov *.avi *.webm);;所有文件 (*)"
        )
        if path:
            self.load_source(Path(path))

    def load_source(self, source: Path) -> None:
        ffprobe = self._candidate("ffprobe", self._settings.ffprobe_path)
        if ffprobe is None or not source.is_file():
            QMessageBox.warning(self, "无法读取视频", "请确认源文件和 FFprobe 路径有效。")
            return
        if self._probe_worker is not None and self._probe_worker.isRunning():
            QMessageBox.information(self, "正在分析", "请等待当前视频分析完成。")
            return
        self._media = None
        self.source_path.setText(str(source))
        self.source_info.setText("正在分析媒体信息…")
        worker = ProbeWorker(ffprobe, source)
        self._probe_worker = worker
        worker.completed.connect(self._show_media)
        worker.failed.connect(self._probe_failed)
        worker.start()

    def _show_media(self, media: MediaInfo) -> None:
        self._media = media
        video = next((s for s in media.streams if s.codec_type == "video"), None)
        audio = next((s for s in media.streams if s.codec_type == "audio"), None)
        detail = [f"时长 {media.duration_seconds:.1f} 秒" if media.duration_seconds else "时长未知"]
        if video:
            detail.append(f"视频 {video.codec_name} · {video.width}×{video.height}")
        if audio:
            detail.append(f"音频 {audio.codec_name} · {audio.channels} 声道")
        self.source_info.setText("   |   ".join(detail))

    def _probe_failed(self, message: str) -> None:
        self._media = None
        self.source_info.setText("视频分析失败")
        QMessageBox.warning(self, "视频分析失败", message)

    def _add_jobs(self, operation: str) -> None:
        ffmpeg = self._candidate("ffmpeg", self._settings.ffmpeg_path)
        if ffmpeg is None or self._media is None:
            QMessageBox.warning(self, "无法添加任务", "请先选择并分析源视频，确认 FFmpeg 可用。")
            return
        if operation == "audio" and not any(s.codec_type == "audio" for s in self._media.streams):
            QMessageBox.warning(self, "无法提取音频", "该媒体文件没有音轨。")
            return
        mode, seconds = ((self.split_mode, self.split_seconds) if operation == "split"
                         else (self.audio_mode, self.audio_seconds))
        segment = seconds.value() if operation != "transcode" and mode.currentData() else None
        folder = (Path(self._settings.default_output_directory)
                  if self._settings.default_output_directory
                  else self._settings_service.suggested_output_directory(self._media.path))
        try:
            jobs = plan_jobs(
                operation, ffmpeg, self._media.path, folder, self._media.duration_seconds,
                segment_seconds=segment, audio_format=self.audio_format.currentData(),
                quality=self.quality.currentData(), reserved=self._reserved,
            )
        except ValueError as error:
            QMessageBox.warning(self, "参数无效", str(error))
            return
        self._jobs.extend(jobs)
        self._states.extend(["等待中"] * len(jobs))
        self._refresh_queue()
        self.command_preview.setPlainText("\n".join(format_command(job.command) for job in jobs))
        self.state_label.setText(f"已添加 {len(jobs)} 个任务")

    def _refresh_queue(self) -> None:
        self.queue.clear()
        for job, state in zip(self._jobs, self._states, strict=True):
            self.queue.addItem(f"{state}  ·  {job.label}  ·  {job.output.name}")

    def _start_next(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            index = self._states.index("等待中")
        except ValueError:
            return
        self._active_index = index
        job = self._jobs[index]
        self._states[index] = "运行中"
        self._refresh_queue()
        self.state_label.setText(f"正在处理：{job.output.name}")
        self.command_preview.setPlainText(format_command(job.command))
        self.progress.setValue(0)
        worker = JobWorker(job)
        self._worker = worker
        worker.progress_changed.connect(self._on_progress)
        worker.log_received.connect(self.log_view.appendPlainText)
        worker.job_finished.connect(self._on_job_finished)
        worker.start()

    def _on_progress(self, percent: int, detail: str) -> None:
        self.progress.setValue(percent)
        self.state_label.setText(detail)

    def _on_job_finished(self, state: str, returncode: int) -> None:
        if self._active_index is not None:
            self._states[self._active_index] = state
        self._refresh_queue()
        self.progress.setValue(100 if state == "已完成" else self.progress.value())
        self.state_label.setText(f"{state} · 退出码 {returncode}")
        self._active_index = None
        if self._worker is not None:
            self._worker.wait()
        self._start_next()

    def _cancel_current(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        files = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if files:
            self.load_source(files[0])
            event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            if not self._worker.wait(5000):
                event.ignore()
                return
        if self._probe_worker is not None and self._probe_worker.isRunning():
            if not self._probe_worker.wait(11000):
                event.ignore()
                return
        super().closeEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self._banner.isNull():
            self._scale_banner(max(1, self.width() - 72))

    def _scale_banner(self, width: int) -> None:
        scaled = self._banner.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        self.brand.setPixmap(scaled)
        self.brand.setFixedHeight(scaled.height())

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #fafbfc; color: #20252b; font-size: 13px; }
            QLabel#brand { font-size: 19px; font-weight: 700; padding: 8px 0 14px 0; }
            QLabel#cardTitle { font-size: 16px; font-weight: 700; }
            QLabel#muted { color: #65707b; }
            QFrame#card { background: white; border: 1px solid #e4e8ec; border-radius: 9px; }
            QFrame#card QLabel { background: transparent; }
            QTabBar { background: #fafbfc; border-bottom: 1px solid #e5e9ed; }
            QTabBar::tab { padding: 11px 18px; color: #5d6874;
                font-family: "Noto Sans SC", "Microsoft YaHei UI";
                font-size: 13px; font-weight: 500; letter-spacing: 0.3px;
                border-bottom: 2px solid transparent; }
            QTabBar::tab:selected { color: #17212b; font-weight: 600;
                border-bottom: 2px solid #1987ce; }
            QLineEdit, QComboBox, QSpinBox, QListWidget, QPlainTextEdit {
                border: 1px solid #dce2e7; border-radius: 5px; padding: 6px; background: white;
            }
            QPushButton { border: 1px solid #dce2e7; border-radius: 5px;
                padding: 8px 13px; background: white; }
            QPushButton:hover { border-color: #1987ce; }
            QPushButton#primary { background: #20252b; color: white;
                border-color: #20252b; font-weight: 600; }
            QProgressBar { border: 0; border-radius: 3px; background: #e7ebef; height: 8px; }
            QProgressBar::chunk { background: #168bd3; border-radius: 3px; }
        """)
