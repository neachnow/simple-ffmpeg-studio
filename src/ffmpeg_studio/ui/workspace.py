"""FFmpeg dashboard with persistent source and processing panels."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QPainter,
    QPainterPath,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_studio import __version__
from ffmpeg_studio.assets import source_path
from ffmpeg_studio.core.ffmpeg import (
    FfmpegError,
    find_executable,
    format_command,
    inspect_executable,
)
from ffmpeg_studio.core.planner import PlannedJob, plan_jobs
from ffmpeg_studio.core.probe import MediaInfo, probe_media
from ffmpeg_studio.core.worker import JobWorker
from ffmpeg_studio.services.history import HistoryService
from ffmpeg_studio.services.settings import AppSettings, SettingsService
from ffmpeg_studio.ui.timeline import ThumbnailWorker, TimelinePanel


def rounded_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    """Round the displayed copy while preserving the original image asset."""
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


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


class AdaptiveStack(QStackedWidget):
    """Size scrollable tab content from the active page, not the tallest page."""

    def sizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.sizeHint() if page is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.minimumSizeHint() if page is not None else super().minimumSizeHint()


class MainWindow(QMainWindow):
    """Each top tab changes settings; source and status stay visible."""

    def __init__(
        self, settings_service: SettingsService, history_service: HistoryService | None = None
    ) -> None:
        super().__init__()
        self._settings_service = settings_service
        self._settings = settings_service.load()
        self._history_service = history_service or HistoryService()
        self._media: MediaInfo | None = None
        self._probe_worker: ProbeWorker | None = None
        self._thumbnail_workers: list[ThumbnailWorker] = []
        self._worker: JobWorker | None = None
        self._jobs: list[PlannedJob] = []
        self._states: list[str] = []
        self._active_index: int | None = None
        self._reserved: set[Path] = set()
        self.setWindowTitle("FFmpeg Studio")
        self.setWindowIcon(QIcon(str(source_path("icon.jfif"))))
        self.resize(1180, 850)
        self.setMinimumSize(900, 640)
        self.setAcceptDrops(True)
        self.setStatusBar(QStatusBar(self))
        self.status_logo = QLabel()
        self.status_logo.setAccessibleName("FFmpeg Studio 状态栏标志")
        logo = QPixmap(str(source_path("logo.jfif")))
        if not logo.isNull():
            title_strip = logo.copy(0, 0, logo.width(), round(logo.height() * 0.215))
            self.status_logo.setPixmap(
                rounded_pixmap(
                    title_strip.scaledToHeight(30, Qt.TransformationMode.SmoothTransformation),
                    4,
                )
            )
            self.statusBar().addPermanentWidget(self.status_logo)
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
        layout.setContentsMargins(36, 16, 36, 16)
        layout.setSpacing(6)
        self.brand = QLabel()
        self.brand.setObjectName("brand")
        self.brand.setAccessibleName("FFmpeg Studio 品牌横幅")
        self._banner = QPixmap(str(source_path("banner.jfif")))
        if self._banner.isNull():
            self.brand.setText("FFmpeg Studio   /   本地媒体工作台")
        else:
            self.brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._scale_banner(1108)
        layout.addWidget(self.brand)
        self.tabs = QTabBar()
        self.tabs.setAccessibleName("功能导航")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        for title in (
            "概览 / Overview", "转码 / Transcode", "视频分割 / Split Video",
            "裁剪 / Trim", "提取音频 / Extract Audio", "设置 / Settings",
        ):
            self.tabs.addTab(title)
        layout.addWidget(self.tabs)
        columns = QHBoxLayout()
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(self._source_card())
        self.timeline = TimelinePanel()
        left.addWidget(self.timeline)
        self.pages = AdaptiveStack()
        self.pages.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        for page in (self._overview_page(), self._transcode_page(), self._split_page(),
                     self._trim_page(), self._audio_page(), self._settings_page()):
            self.pages.addWidget(page)
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_scroll.setWidget(self.pages)
        left.addWidget(self.page_scroll, 1)
        columns.addLayout(left, 7)
        columns.addWidget(self._status_card(), 4)
        layout.addLayout(columns, 1)
        self.tabs.currentChanged.connect(self._change_page)
        self.timeline.cuts_changed.connect(self._on_timeline_cuts)
        self.timeline.trim_changed.connect(self._on_timeline_trim)
        return root

    def _change_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.pages.updateGeometry()
        self.pages.resize(self.pages.width(), self.pages.sizeHint().height())
        self.timeline.set_mode({2: "split", 3: "trim", 4: "audio"}.get(index, "view"))
        self.page_scroll.verticalScrollBar().setValue(0)

    def _source_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(4)
        heading_row = QHBoxLayout()
        heading = QLabel("源视频")
        heading.setObjectName("cardTitle")
        heading_row.addWidget(heading)
        self.source_info = QLabel("尚未选择视频")
        self.source_info.setObjectName("muted")
        self.source_info.setWordWrap(False)
        heading_row.addSpacing(16)
        heading_row.addWidget(self.source_info, 1)
        layout.addLayout(heading_row)
        row = QHBoxLayout()
        self.source_path = QLineEdit()
        self.source_path.setPlaceholderText("拖入视频，或选择本地文件")
        self.source_path.setReadOnly(True)
        self.source_path.setAccessibleName("当前源视频路径")
        choose = QPushButton("选择视频")
        choose.clicked.connect(self._choose_source)
        row.addWidget(self.source_path, 1)
        row.addWidget(choose)
        layout.addLayout(row)
        return card

    def _form_page(self, title: str, description: str) -> tuple[QFrame, QVBoxLayout, QFormLayout]:
        page = QFrame()
        page.setObjectName("formPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(7)
        heading_row = QHBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        heading_row.addWidget(heading)
        heading_row.addSpacing(14)
        note = QLabel(description)
        note.setWordWrap(False)
        note.setObjectName("muted")
        note.setToolTip(description)
        heading_row.addWidget(note, 1)
        layout.addLayout(heading_row)
        form = QFormLayout()
        form.setSpacing(7)
        layout.addLayout(form)
        return page, layout, form

    @staticmethod
    def _parameter_grid(
        form: QFormLayout, rows: tuple[tuple[tuple[str, QWidget], ...], ...]
    ) -> None:
        """Use four fixed-width columns, leaving the last cell empty on short rows."""
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        for row_index, row in enumerate(rows):
            for column, (label, field) in enumerate(row):
                cell = QFrame()
                cell.setObjectName("parameterCell")
                cell.setAccessibleName(label)
                cell_layout = QVBoxLayout(cell)
                cell_layout.setContentsMargins(8, 6, 8, 6)
                cell_layout.setSpacing(3)
                caption = QLabel(label)
                caption.setObjectName("muted")
                cell_layout.addWidget(caption)
                field.setMinimumWidth(0)
                field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                cell_layout.addWidget(field)
                grid.addWidget(cell, row_index, column)
        form.addRow(container)

    def _overview_page(self) -> QFrame:
        page, layout, _ = self._form_page(
            "开始处理", "选择源视频后，在上方切换功能。参数位于左侧，处理进度与日志显示在右侧。"
        )
        self.environment_label = QLabel("正在检测 FFmpeg 环境…")
        self.environment_label.setWordWrap(True)
        self.environment_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.environment_label.setObjectName("muted")
        layout.addWidget(self.environment_label)
        layout.addWidget(QLabel("最近完成的任务"))
        self.history_list = QListWidget()
        self.history_list.setAccessibleName("最近任务历史")
        self.history_list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.history_list)
        self._refresh_history()
        layout.addStretch()
        return page

    def _refresh_history(self) -> None:
        self.history_list.clear()
        records = self._history_service.load()
        if not records:
            self.history_list.addItem("暂无历史任务")
        for record in records:
            self.history_list.addItem(
                f"{record.finished_at[:16]}  ·  {record.state}  ·  {Path(record.output).name}"
            )

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
    def _duration_controls(form: QFormLayout | None) -> tuple[QComboBox, QSpinBox]:
        mode = QComboBox()
        mode.addItem("按原时长（完整输出）", "full")
        mode.addItem("按每段时长分割", "fixed")
        mode.addItem("按时间轴切点", "cuts")
        seconds = QSpinBox()
        seconds.setRange(1, 86400)
        seconds.setValue(60)
        seconds.setSuffix(" 秒 / 段")
        seconds.setEnabled(False)
        mode.currentIndexChanged.connect(lambda: seconds.setEnabled(mode.currentData() == "fixed"))
        if form is not None:
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
        self.audio_mode, self.audio_seconds = self._duration_controls(None)
        self.audio_format = QComboBox()
        for name in ("MP3", "AAC", "WAV", "FLAC"):
            self.audio_format.addItem(name, name.lower())
        self.audio_bitrate = QComboBox()
        for bitrate in ("128k", "192k", "256k", "320k"):
            self.audio_bitrate.addItem(bitrate, bitrate)
        self.audio_bitrate.setCurrentIndex(1)
        self.audio_sample_rate = QComboBox()
        for label, value in (("保持原采样率", None), ("44.1 kHz", 44100), ("48 kHz", 48000)):
            self.audio_sample_rate.addItem(label, value)
        self.audio_channels = QComboBox()
        for label, value in (("保持原声道", None), ("单声道", 1), ("立体声", 2)):
            self.audio_channels.addItem(label, value)
        self.audio_gain = QSpinBox()
        self.audio_gain.setRange(-12, 12)
        self.audio_gain.setSuffix(" dB")
        self._parameter_grid(form, (
            (("处理范围", self.audio_mode), ("每段时长", self.audio_seconds),
             ("输出格式", self.audio_format), ("音频码率", self.audio_bitrate)),
            (("采样率", self.audio_sample_rate), ("声道", self.audio_channels),
             ("音量增益", self.audio_gain)),
        ))
        button = QPushButton("添加音频提取任务")
        button.setObjectName("primary")
        button.clicked.connect(lambda: self._add_jobs("audio"))
        layout.addWidget(button)
        layout.addStretch()
        return page

    def _trim_page(self) -> QFrame:
        page, layout, form = self._form_page(
            "裁剪与变换",
            "按开始和结束时间截取视频，可选旋转、翻转及画面裁切。结束时间填 0 表示到片尾。",
        )
        self.trim_start = QDoubleSpinBox()
        self.trim_start.setRange(0, 864000)
        self.trim_start.setDecimals(2)
        self.trim_start.setSingleStep(0.1)
        self.trim_start.setSuffix(" 秒")
        self.trim_end = QDoubleSpinBox()
        self.trim_end.setRange(0, 864000)
        self.trim_end.setDecimals(2)
        self.trim_end.setSingleStep(0.1)
        self.trim_end.setSuffix(" 秒")
        self.trim_end.setToolTip("填写 0 表示到视频末尾")
        self.trim_rotation = QComboBox()
        for label, value in (("不变", "none"), ("顺时针 90°", "clockwise"),
                             ("逆时针 90°", "counterclockwise"),
                             ("水平翻转", "flip_horizontal"), ("垂直翻转", "flip_vertical")):
            self.trim_rotation.addItem(label, value)
        self.crop_width = QSpinBox()
        self.crop_width.setRange(0, 16384)
        self.crop_width.setSpecialValueText("不裁切")
        self.crop_height = QSpinBox()
        self.crop_height.setRange(0, 16384)
        self.crop_height.setSpecialValueText("不裁切")
        self.crop_x = QSpinBox()
        self.crop_x.setRange(0, 16384)
        self.crop_y = QSpinBox()
        self.crop_y.setRange(0, 16384)
        self._parameter_grid(form, (
            (("开始时间", self.trim_start), ("结束时间", self.trim_end),
             ("旋转 / 翻转", self.trim_rotation), ("裁切宽度", self.crop_width)),
            (("裁切高度", self.crop_height), ("起点 X", self.crop_x),
             ("起点 Y", self.crop_y)),
        ))
        self.trim_start.valueChanged.connect(self._sync_trim_fields)
        self.trim_end.valueChanged.connect(self._sync_trim_fields)
        button = QPushButton("添加裁剪任务")
        button.setObjectName("primary")
        button.clicked.connect(lambda: self._add_jobs("trim"))
        layout.addWidget(button)
        layout.addStretch()
        page.setMinimumHeight(220)
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
        clear = QPushButton("清除任务历史")
        clear.clicked.connect(self._clear_history)
        layout.addWidget(clear)
        version = QLabel(f"FFmpeg Studio {__version__}")
        version.setObjectName("muted")
        layout.addWidget(version)
        layout.addStretch()
        return page

    def _clear_history(self) -> None:
        answer = QMessageBox.question(self, "清除任务历史", "确定清除本机保存的任务历史吗？")
        if answer == QMessageBox.StandardButton.Yes:
            self._history_service.clear()
            self._refresh_history()

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
        self.queue.setAccessibleName("处理任务队列")
        self.queue.setToolTip("选择等待中的任务可编辑输出、排序或移除；失败任务可重试。")
        self.queue.setMinimumHeight(150)
        self.queue.currentRowChanged.connect(self._preview_selected)
        layout.addWidget(self.queue, 2)
        for actions in (
            (("编辑输出", self._edit_selected_output), ("移除", self._remove_selected),
             ("重试", self._retry_selected)),
            (("上移", lambda: self._move_selected(-1)),
             ("下移", lambda: self._move_selected(1)),
             ("打开位置", self._open_selected_output)),
        ):
            queue_actions = QHBoxLayout()
            for label, handler in actions:
                button = QPushButton(label)
                button.clicked.connect(handler)
                queue_actions.addWidget(button)
            layout.addLayout(queue_actions)
        layout.addWidget(QLabel("命令预览"))
        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setMaximumHeight(100)
        layout.addWidget(self.command_preview)
        layout.addWidget(QLabel("执行日志"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setAccessibleName("FFmpeg 执行日志")
        layout.addWidget(self.log_view, 2)
        return card

    def _candidate(self, name: str, preferred: str) -> Path | None:
        if preferred:
            return find_executable(preferred, name)
        bundled = source_path("ffmpeg", "bin", f"{name}.exe")
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
        for thumbnail_worker in self._thumbnail_workers:
            thumbnail_worker.cancel()
        self._media = None
        self.timeline.set_media(0)
        self.source_path.setText(str(source))
        self.source_info.setText("正在分析媒体信息…")
        worker = ProbeWorker(ffprobe, source)
        self._probe_worker = worker
        worker.completed.connect(self._show_media)
        worker.failed.connect(self._probe_failed)
        worker.start()

    def _show_media(self, media: MediaInfo) -> None:
        self._media = media
        self.trim_start.blockSignals(True)
        self.trim_end.blockSignals(True)
        self.trim_start.setValue(0)
        self.trim_end.setValue(0)
        self.trim_start.blockSignals(False)
        self.trim_end.blockSignals(False)
        video = next((s for s in media.streams if s.codec_type == "video"), None)
        audio = next((s for s in media.streams if s.codec_type == "audio"), None)
        self.timeline.set_media(media.duration_seconds or 0.0, has_video=video is not None)
        detail = [f"时长 {media.duration_seconds:.1f} 秒" if media.duration_seconds else "时长未知"]
        if video:
            detail.append(f"视频 {video.codec_name} · {video.width}×{video.height}")
        if audio:
            detail.append(f"音频 {audio.codec_name} · {audio.channels} 声道")
        self.source_info.setText("   |   ".join(detail))
        ffmpeg = self._candidate("ffmpeg", self._settings.ffmpeg_path)
        if (video and ffmpeg and media.duration_seconds and media.duration_seconds > 0
                and media.path.is_file() and media.path.stat().st_size > 0):
            worker = ThumbnailWorker(ffmpeg, media.path, media.duration_seconds)
            self._thumbnail_workers.append(worker)
            worker.frame_ready.connect(self._on_thumbnail_frame)
            worker.finished.connect(lambda worker=worker: self._release_thumbnail_worker(worker))
            worker.start()
        else:
            self.timeline.set_preview_finished()

    def _on_thumbnail_frame(self, source: str, index: int, data: bytes) -> None:
        if self._media is not None and str(self._media.path) == source:
            self.timeline.set_frame(index, data)

    def _release_thumbnail_worker(self, worker: ThumbnailWorker) -> None:
        if self._media is not None and self._media.path == worker.source:
            self.timeline.set_preview_finished()
        if worker in self._thumbnail_workers:
            self._thumbnail_workers.remove(worker)
        worker.deleteLater()

    def _on_timeline_cuts(self, mode: str, cuts: object) -> None:
        control = self.split_mode if mode == "split" else self.audio_mode
        if cuts:
            control.setCurrentIndex(control.findData("cuts"))
        elif control.currentData() == "cuts":
            control.setCurrentIndex(control.findData("full"))

    def _on_timeline_trim(self, start: float, end: float) -> None:
        self.trim_start.blockSignals(True)
        self.trim_end.blockSignals(True)
        self.trim_start.setValue(start)
        full_length = self._media.duration_seconds if self._media is not None else None
        self.trim_end.setValue(0 if full_length and abs(end - full_length) < 0.01 else end)
        self.trim_start.blockSignals(False)
        self.trim_end.blockSignals(False)

    def _sync_trim_fields(self) -> None:
        if self._media is None or not self._media.duration_seconds:
            return
        end = self.trim_end.value() or self._media.duration_seconds
        if end > self.trim_start.value():
            self.timeline.set_trim_range(self.trim_start.value(), end)

    def _probe_failed(self, message: str) -> None:
        self._media = None
        self.timeline.set_media(0)
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
        segment = None
        cut_points = None
        if operation in {"split", "audio"}:
            mode, seconds = ((self.split_mode, self.split_seconds) if operation == "split"
                             else (self.audio_mode, self.audio_seconds))
            if mode.currentData() == "fixed":
                segment = seconds.value()
            elif mode.currentData() == "cuts":
                cut_points = self.timeline.cuts(operation)
        crop = None
        if operation == "trim" and (self.crop_width.value() or self.crop_height.value()):
            crop = (self.crop_width.value(), self.crop_height.value(),
                    self.crop_x.value(), self.crop_y.value())
        video = next((s for s in self._media.streams if s.codec_type == "video"), None)
        video_size = (video.width, video.height) if video and video.width and video.height else None
        folder = (Path(self._settings.default_output_directory)
                  if self._settings.default_output_directory
                  else self._settings_service.suggested_output_directory(self._media.path))
        try:
            jobs = plan_jobs(
                operation, ffmpeg, self._media.path, folder, self._media.duration_seconds,
                segment_seconds=segment, cut_points=cut_points,
                audio_format=self.audio_format.currentData(),
                quality=self.quality.currentData(), reserved=self._reserved,
                start_seconds=self.trim_start.value(),
                end_seconds=self.trim_end.value() or None,
                rotation=self.trim_rotation.currentData(), crop=crop, video_size=video_size,
                audio_bitrate=self.audio_bitrate.currentData(),
                sample_rate=self.audio_sample_rate.currentData(),
                channels=self.audio_channels.currentData(), gain_db=self.audio_gain.value(),
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
        selected = self.queue.currentRow()
        self.queue.clear()
        for job, state in zip(self._jobs, self._states, strict=True):
            self.queue.addItem(f"{state}  ·  {job.label}  ·  {job.output.name}")
        if 0 <= selected < self.queue.count():
            self.queue.setCurrentRow(selected)

    def _preview_selected(self, index: int) -> None:
        if 0 <= index < len(self._jobs):
            self.command_preview.setPlainText(format_command(self._jobs[index].command))

    def _selected_index(self) -> int | None:
        index = self.queue.currentRow()
        return index if 0 <= index < len(self._jobs) else None

    def _edit_selected_output(self) -> None:
        index = self._selected_index()
        if index is None or self._states[index] != "等待中":
            return
        job = self._jobs[index]
        value, accepted = QInputDialog.getText(
            self, "编辑任务输出", "输出文件路径", text=str(job.output)
        )
        if not accepted or value.strip() == str(job.output):
            return
        new_path = Path(value.strip())
        if (not value.strip() or new_path.suffix.lower() != job.output.suffix.lower()
                or new_path.exists() or new_path in self._reserved
                or new_path == Path(job.command[job.command.index("-i") + 1])):
            QMessageBox.warning(self, "输出路径无效", "请填写未被占用的同格式输出文件路径。")
            return
        self._reserved.discard(job.output)
        self._reserved.add(new_path)
        self._jobs[index] = replace(
            job, output=new_path, command=(*job.command[:-1], str(new_path))
        )
        self._refresh_queue()
        self._preview_selected(index)

    def _remove_selected(self) -> None:
        index = self._selected_index()
        if index is None or self._states[index] != "等待中":
            return
        self._reserved.discard(self._jobs[index].output)
        del self._jobs[index]
        del self._states[index]
        self._refresh_queue()

    def _move_selected(self, offset: int) -> None:
        index = self._selected_index()
        if index is None:
            return
        target = index + offset
        if not 0 <= target < len(self._jobs):
            return
        if self._states[index] != "等待中" or self._states[target] != "等待中":
            return
        for values in (self._jobs, self._states):
            values[index], values[target] = values[target], values[index]
        self._refresh_queue()
        self.queue.setCurrentRow(target)

    def _retry_selected(self) -> None:
        index = self._selected_index()
        if index is None or self._states[index] not in {"失败", "已取消"}:
            return
        original = self._jobs[index]
        candidate = original.output
        number = 2
        while candidate.exists() or candidate in self._reserved:
            candidate = original.output.with_name(
                f"{original.output.stem} ({number}){original.output.suffix}"
            )
            number += 1
        self._reserved.add(candidate)
        retried = replace(
            original, output=candidate, command=(*original.command[:-1], str(candidate))
        )
        self._jobs.append(retried)
        self._states.append("等待中")
        self._refresh_queue()
        self.queue.setCurrentRow(len(self._jobs) - 1)

    def _open_selected_output(self) -> None:
        index = self._selected_index()
        if index is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._jobs[index].output.parent)))

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
            job = self._jobs[self._active_index]
            try:
                self._history_service.add(job.label, job.output, state, returncode)
                self._refresh_history()
            except OSError as error:
                self.log_view.appendPlainText(f"无法保存任务历史：{error}")
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
        for thumbnail_worker in self._thumbnail_workers:
            thumbnail_worker.cancel()
        for thumbnail_worker in self._thumbnail_workers:
            if not thumbnail_worker.wait(13000):
                event.ignore()
                return
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
        self.brand.setPixmap(rounded_pixmap(scaled, 10))
        self.brand.setFixedHeight(scaled.height())

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #fafbfc; color: #20252b; font-size: 13px; }
            QLabel#brand { font-size: 19px; font-weight: 700; padding: 0; }
            QLabel#cardTitle { font-size: 16px; font-weight: 700; }
            QLabel#muted { color: #65707b; }
            QFrame#card { background: white; border: 1px solid #e4e8ec; border-radius: 9px; }
            QFrame#formPage { background: white; border: 1px solid #e4e8ec;
                border-radius: 9px; }
            QFrame#parameterCell { background: #f8fafb; border: 1px solid #e2e8ed;
                border-radius: 6px; }
            QFrame#card QLabel, QFrame#formPage QLabel { background: transparent; }
            QTabBar { background: #fafbfc; border-bottom: 1px solid #e5e9ed; }
            QTabBar::tab { padding: 11px 18px; color: #5d6874;
                font-family: "Noto Sans SC", "Microsoft YaHei UI";
                font-size: 13px; font-weight: 500; letter-spacing: 0.3px;
                border-bottom: 2px solid transparent; }
            QTabBar::tab:selected { color: #17212b; font-weight: 600;
                border-bottom: 2px solid #1987ce; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QPlainTextEdit {
                border: 1px solid #dce2e7; border-radius: 5px; padding: 6px; background: white;
            }
            QPushButton { border: 1px solid #dce2e7; border-radius: 5px;
                padding: 8px 13px; background: white; }
            QPushButton:hover { border-color: #1987ce; }
            QPushButton#primary { background: #20252b; color: white;
                border-color: #20252b; font-weight: 600; }
            QFrame#formPage QPushButton { padding: 5px 10px; }
            QProgressBar { border: 0; border-radius: 3px; background: #e7ebef; height: 8px; }
            QProgressBar::chunk { background: #168bd3; border-radius: 3px; }
        """)
