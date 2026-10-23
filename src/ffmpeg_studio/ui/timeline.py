"""Interactive, zoomable media ruler with video thumbnails and cut markers."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_studio.core.ffmpeg import MEDIA_PROCESS_CREATION_FLAGS


def format_time(seconds: float) -> str:
    """A compact media timestamp, retaining sub-second precision when useful."""
    whole, centiseconds = divmod(round(seconds * 100), 100)
    minutes, second = divmod(whole, 60)
    hours, minute = divmod(minutes, 60)
    label = f"{hours:02d}:{minute:02d}:{second:02d}" if hours else f"{minute:02d}:{second:02d}"
    return f"{label}.{centiseconds:02d}" if centiseconds else label


def tick_step(duration: float, zoom: int, width: int) -> float:
    """Choose readable 1/2/5-based ruler units for the current scale."""
    if duration <= 0:
        return 1.0
    target = max(0.01, duration / max(1, zoom * width / 90))
    base = 10 ** math.floor(math.log10(target))
    return next(multiplier * base for multiplier in (1, 2, 5, 10)
                if multiplier * base >= target)


class ThumbnailWorker(QThread):
    """Seek a few frames in the background; no files are written to disk."""

    frame_ready = Signal(str, int, bytes)

    def __init__(self, ffmpeg: Path, source: Path, duration: float, count: int = 8) -> None:
        super().__init__()
        self.ffmpeg = ffmpeg
        self.source = source
        self.duration = duration
        self.count = count
        self._cancelled = False
        self._process: subprocess.Popen[bytes] | None = None

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def run(self) -> None:
        for index in range(self.count):
            if self._cancelled:
                return
            position = max(0.0, min(self.duration - 0.05,
                                    self.duration * (index + 0.5) / self.count))
            command = [
                str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
                "-ss", f"{position:.3f}", "-i", str(self.source), "-frames:v", "1",
                "-vf", "scale=160:-1", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1",
            ]
            try:
                process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=MEDIA_PROCESS_CREATION_FLAGS,
                )
                self._process = process
                data, _ = process.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                data = b""
            except OSError:
                data = b""
            finally:
                self._process = None
            if data and not self._cancelled:
                self.frame_ready.emit(str(self.source), index, data)


class TimelineStrip(QWidget):
    """Ruler and filmstrip. Left click adds/drags cuts; right click removes one."""

    cuts_changed = Signal(str, object)
    trim_changed = Signal(float, float)
    selection_changed = Signal()

    HEIGHT = 152
    TRACK_TOP = 29
    TRACK_HEIGHT = 120
    TRACK_BOTTOM = TRACK_TOP + TRACK_HEIGHT

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(1)
        self.setMouseTracking(True)
        self.setAccessibleName("视频时间标尺及切点画面条")
        self.duration = 0.0
        self.zoom = 1
        self.mode = "view"
        self.frames: list[QImage] = []
        self.has_video = True
        self.preview_pending = False
        self._cuts: dict[str, list[float]] = {"split": [], "audio": []}
        self.selected_cut: int | None = None
        self.trim_start = 0.0
        self.trim_end = 0.0
        self._trim_next = "start"
        self._dragging: tuple[str, int | None] | None = None

    def set_media(self, duration: float, *, has_video: bool = True) -> None:
        self.duration = max(0.0, duration)
        self.frames = []
        self.has_video = has_video
        self.preview_pending = has_video and self.duration > 0
        self._cuts = {"split": [], "audio": []}
        self.selected_cut = None
        self.trim_start = 0.0
        self.trim_end = self.duration
        self._trim_next = "start"
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.selected_cut = None
        self._dragging = None
        self.update()

    def set_frames(self, frames: list[QImage]) -> None:
        self.frames = frames
        self.update()

    def set_preview_finished(self) -> None:
        self.preview_pending = False
        self.update()

    def cuts(self, mode: str) -> tuple[float, ...]:
        return tuple(self._cuts.get(mode, []))

    def add_cut(self, seconds: float) -> bool:
        if self.mode not in self._cuts or self.duration <= 0:
            return False
        point = round(seconds, 3)
        if not 0.01 <= point <= self.duration - 0.01:
            return False
        cuts = self._cuts[self.mode]
        if len(cuts) >= 499 or any(abs(point - old) < 0.01 for old in cuts):
            return False
        cuts.append(point)
        cuts.sort()
        self.selected_cut = cuts.index(point)
        self.cuts_changed.emit(self.mode, self.cuts(self.mode))
        self.selection_changed.emit()
        self.update()
        return True

    def remove_selected(self) -> None:
        if self.mode not in self._cuts or self.selected_cut is None:
            return
        cuts = self._cuts[self.mode]
        if 0 <= self.selected_cut < len(cuts):
            del cuts[self.selected_cut]
            self.selected_cut = None
            self.cuts_changed.emit(self.mode, self.cuts(self.mode))
            self.selection_changed.emit()
            self.update()

    def clear_marks(self) -> None:
        if self.mode in self._cuts:
            self._cuts[self.mode].clear()
            self.selected_cut = None
            self.cuts_changed.emit(self.mode, self.cuts(self.mode))
            self.selection_changed.emit()
        elif self.mode == "trim":
            self.set_trim_range(0.0, self.duration, emit=True)
            self._trim_next = "start"
        self.update()

    def set_trim_range(self, start: float, end: float, *, emit: bool = False) -> None:
        if self.duration <= 0:
            self.trim_start = self.trim_end = 0.0
        else:
            self.trim_start = max(0.0, min(start, self.duration - 0.01))
            self.trim_end = max(self.trim_start + 0.01, min(end, self.duration))
        if emit:
            self.trim_changed.emit(self.trim_start, self.trim_end)
        self.update()

    def time_for_x(self, x: float) -> float:
        return max(0.0, min(self.duration, x / max(1, self.width() - 1) * self.duration))

    def x_for_time(self, seconds: float) -> float:
        return seconds / self.duration * (self.width() - 1) if self.duration else 0.0

    def _nearest_cut(self, x: float) -> int | None:
        if self.mode not in self._cuts:
            return None
        cuts = self._cuts[self.mode]
        if not cuts:
            return None
        nearest = min(range(len(cuts)), key=lambda index: abs(self.x_for_time(cuts[index]) - x))
        return nearest if abs(self.x_for_time(cuts[nearest]) - x) <= 8 else None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.duration <= 0 or event.position().y() < self.TRACK_TOP:
            return
        x = event.position().x()
        if self.mode in self._cuts:
            nearby = self._nearest_cut(x)
            if event.button() == Qt.MouseButton.RightButton and nearby is not None:
                self.selected_cut = nearby
                self.remove_selected()
            elif event.button() == Qt.MouseButton.LeftButton:
                if nearby is None:
                    self.add_cut(self.time_for_x(x))
                else:
                    self.selected_cut = nearby
                    self.selection_changed.emit()
                    self.update()
                if self.selected_cut is not None:
                    self._dragging = ("cut", self.selected_cut)
        elif self.mode == "trim" and event.button() == Qt.MouseButton.LeftButton:
            start_distance = abs(self.x_for_time(self.trim_start) - x)
            end_distance = abs(self.x_for_time(self.trim_end) - x)
            if min(start_distance, end_distance) <= 8:
                target = "start" if start_distance <= end_distance else "end"
            else:
                target = self._trim_next
                self._trim_next = "end" if target == "start" else "start"
            self._dragging = (target, None)
            self._move_trim(target, self.time_for_x(x))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        kind, index = self._dragging
        point = round(self.time_for_x(event.position().x()), 3)
        if kind == "cut" and index is not None:
            cuts = self._cuts[self.mode]
            lower = cuts[index - 1] + 0.01 if index else 0.01
            upper = cuts[index + 1] - 0.01 if index + 1 < len(cuts) else self.duration - 0.01
            cuts[index] = max(lower, min(point, upper))
            self.cuts_changed.emit(self.mode, self.cuts(self.mode))
            self.update()
        elif kind in {"start", "end"}:
            self._move_trim(kind, point)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = None
        super().mouseReleaseEvent(event)

    def _move_trim(self, target: str, point: float) -> None:
        if target == "start":
            self.trim_start = max(0.0, min(point, self.trim_end - 0.01))
        else:
            self.trim_end = min(self.duration, max(point, self.trim_start + 0.01))
        self.trim_changed.emit(self.trim_start, self.trim_end)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafb"))
        painter.setPen(QPen(QColor("#aeb8c1"), 1))
        painter.drawLine(0, 25, self.width(), 25)
        painter.fillRect(
            QRectF(0, self.TRACK_TOP, self.width(), self.TRACK_HEIGHT),
            QColor("#26323b"),
        )
        if self.duration <= 0:
            painter.setPen(QColor("#d5dce1"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择视频后显示时间轴")
            return
        tile_width = 200
        visible = event.rect()
        first = max(0, visible.left() // tile_width)
        last = min(math.ceil(self.width() / tile_width), visible.right() // tile_width + 2)
        for tile in range(first, last):
            x = tile * tile_width
            rect = QRectF(
                x, self.TRACK_TOP + 1,
                min(tile_width - 1, self.width() - x), self.TRACK_HEIGHT - 1,
            )
            if self.frames:
                frame_index = min(len(self.frames) - 1,
                                  int((x + tile_width / 2) / self.width() * len(self.frames)))
                frame = self.frames[frame_index]
                if not frame.isNull():
                    painter.drawImage(rect, frame)
            painter.setPen(QPen(QColor("#60717c"), 1))
            painter.drawLine(x, self.TRACK_TOP, x, self.TRACK_BOTTOM)
        if not any(not frame.isNull() for frame in self.frames):
            if not self.has_video:
                message = "该媒体没有视频画面"
            elif self.preview_pending:
                message = "正在生成视频画面预览…"
            else:
                message = "无法生成画面预览，仍可按标尺设置时间"
            painter.setPen(QColor("#d5dce1"))
            painter.drawText(QRectF(0, self.TRACK_TOP, self.width(), self.TRACK_HEIGHT),
                             Qt.AlignmentFlag.AlignCenter, message)
        step = tick_step(self.duration, self.zoom, self.width() // self.zoom)
        count = min(2000, math.floor(self.duration / step) + 1)
        for index in range(count + 1):
            moment = min(self.duration, index * step)
            x = round(self.x_for_time(moment))
            if x < visible.left() - 70 or x > visible.right() + 70:
                continue
            painter.setPen(QPen(QColor("#8d9da9"), 1))
            painter.drawLine(x, 18, x, 25)
            painter.setPen(QColor("#51616d"))
            painter.drawText(x + 3, 14, format_time(moment))
        if self.mode in self._cuts:
            for index, moment in enumerate(self._cuts[self.mode]):
                self._draw_marker(painter, moment, index == self.selected_cut)
        elif self.mode == "trim":
            start_x = self.x_for_time(self.trim_start)
            end_x = self.x_for_time(self.trim_end)
            painter.fillRect(
                QRectF(0, self.TRACK_TOP, start_x, self.TRACK_HEIGHT),
                QColor(0, 0, 0, 145),
            )
            painter.fillRect(QRectF(end_x, self.TRACK_TOP,
                                    self.width() - end_x, self.TRACK_HEIGHT),
                             QColor(0, 0, 0, 145))
            self._draw_marker(painter, self.trim_start, False, QColor("#28bbca"))
            self._draw_marker(painter, self.trim_end, False, QColor("#28bbca"))

    def _draw_marker(
        self, painter: QPainter, moment: float, selected: bool,
        color: QColor | None = None,
    ) -> None:
        x = self.x_for_time(moment)
        shade = color or QColor("#f1704f" if not selected else "#f4af43")
        painter.setPen(QPen(shade, 2))
        painter.drawLine(QPointF(x, 14), QPointF(x, self.TRACK_BOTTOM))
        painter.setBrush(shade)
        painter.drawEllipse(QPointF(x, 29), 4, 4)


class TimelinePanel(QFrame):
    """Persistent left-side timeline with per-function cut sets and zoom control."""

    cuts_changed = Signal(str, object)
    trim_changed = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setFixedHeight(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(5)
        top = QHBoxLayout()
        title = QLabel("视频时间轴 / Timeline")
        title.setObjectName("cardTitle")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("缩放"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 16)
        self.zoom_slider.setValue(1)
        self.zoom_slider.setFixedWidth(105)
        self.zoom_slider.setAccessibleName("时间标尺缩放")
        top.addWidget(self.zoom_slider)
        self.zoom_label = QLabel("×1")
        top.addWidget(self.zoom_label)
        layout.addLayout(top)
        self.strip = TimelineStrip()
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setWidgetResizable(False)
        self.scroll.setFixedHeight(168)
        self.scroll.setWidget(self.strip)
        layout.addWidget(self.scroll)
        bottom = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        bottom.addWidget(self.hint, 1)
        self.remove_button = QPushButton("删除选中线")
        self.remove_button.clicked.connect(self.strip.remove_selected)
        bottom.addWidget(self.remove_button)
        self.clear_button = QPushButton("清空")
        self.clear_button.clicked.connect(self.strip.clear_marks)
        bottom.addWidget(self.clear_button)
        layout.addLayout(bottom)
        self.zoom_slider.valueChanged.connect(self._set_zoom)
        self.strip.cuts_changed.connect(self._on_cuts_changed)
        self.strip.trim_changed.connect(self.trim_changed)
        self.strip.selection_changed.connect(self._refresh_hint)
        self.set_mode("view")

    def set_media(self, duration: float, *, has_video: bool = True) -> None:
        self.zoom_slider.setValue(1)
        self.strip.set_media(duration, has_video=has_video)
        self._update_width()
        self._set_zoom(1)
        self._refresh_hint()

    def set_frame(self, index: int, data: bytes, count: int = 8) -> None:
        if len(self.strip.frames) != count:
            self.strip.frames = [QImage() for _ in range(count)]
        self.strip.frames[index] = QImage.fromData(data)
        self.strip.update()

    def set_mode(self, mode: str) -> None:
        self.strip.set_mode(mode)
        self.remove_button.setVisible(mode in {"split", "audio"})
        self.clear_button.setVisible(mode in {"split", "audio", "trim"})
        self._refresh_hint()

    def cuts(self, mode: str) -> tuple[float, ...]:
        return self.strip.cuts(mode)

    def set_trim_range(self, start: float, end: float) -> None:
        self.strip.set_trim_range(start, end)

    def set_preview_finished(self) -> None:
        self.strip.set_preview_finished()

    def _on_cuts_changed(self, mode: str, cuts: object) -> None:
        self._refresh_hint()
        self.cuts_changed.emit(mode, cuts)

    def _refresh_hint(self) -> None:
        if self.strip.duration <= 0:
            value = "选择视频后可缩放标尺并设置时间点"
        elif self.strip.mode in {"split", "audio"}:
            count = len(self.strip.cuts(self.strip.mode))
            selected = self.strip.selected_cut
            detail = (f" · 选中 {format_time(self.strip.cuts(self.strip.mode)[selected])}"
                      if selected is not None else "")
            value = f"点击加线，拖动微调，右键删除 · {count} 个切点{detail}"
        elif self.strip.mode == "trim":
            value = (f"入 {format_time(self.strip.trim_start)} → "
                     f"出 {format_time(self.strip.trim_end)} · 点击或拖动青色线")
        else:
            value = "切换到分割、裁剪或提取音频可选择时间范围"
        self.hint.setText(value)

    def _set_zoom(self, zoom: int) -> None:
        bar = self.scroll.horizontalScrollBar()
        old_width = max(1, self.strip.width())
        center_ratio = (bar.value() + self.scroll.viewport().width() / 2) / old_width
        self.strip.zoom = zoom
        self._update_width()
        bar.setValue(round(center_ratio * self.strip.width() - self.scroll.viewport().width() / 2))
        step = tick_step(self.strip.duration, zoom, self.scroll.viewport().width())
        self.zoom_label.setText(f"×{zoom} · {format_time(step)}/格")

    def _update_width(self) -> None:
        self.strip.setFixedWidth(max(1, self.scroll.viewport().width()) * self.strip.zoom)
        self.strip.update()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._update_width()
