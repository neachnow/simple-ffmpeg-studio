"""Visual timeline interactions and their planned FFmpeg jobs."""

import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSettings, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ffmpeg_studio.core.ffmpeg import MEDIA_PROCESS_CREATION_FLAGS
from ffmpeg_studio.core.probe import MediaInfo, MediaStream
from ffmpeg_studio.services.history import HistoryService
from ffmpeg_studio.services.settings import SettingsService
from ffmpeg_studio.ui.timeline import ThumbnailWorker, TimelinePanel, format_time, tick_step
from ffmpeg_studio.ui.workspace import MainWindow


def test_ruler_zoom_mouse_cuts_and_trim_range(qt_app: QApplication) -> None:
    panel = TimelinePanel()
    panel.resize(680, 180)
    panel.show()
    qt_app.processEvents()
    panel.set_media(100)
    panel.set_mode("split")
    strip = panel.strip
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton,
                     pos=QPoint(round(strip.x_for_time(20)), 50))
    assert strip.cuts("split") == pytest.approx((20,), abs=0.2)
    QTest.mousePress(strip, Qt.MouseButton.LeftButton,
                     pos=QPoint(round(strip.x_for_time(20)), 50))
    QTest.mouseMove(strip, QPoint(round(strip.x_for_time(30)), 50))
    QTest.mouseRelease(strip, Qt.MouseButton.LeftButton,
                       pos=QPoint(round(strip.x_for_time(30)), 50))
    assert strip.cuts("split") == pytest.approx((30,), abs=0.2)
    QTest.mouseClick(strip, Qt.MouseButton.RightButton,
                     pos=QPoint(round(strip.x_for_time(30)), 50))
    assert strip.cuts("split") == ()
    assert strip.add_cut(20)
    panel.zoom_slider.setValue(4)
    qt_app.processEvents()
    assert strip.width() >= panel.scroll.viewport().width() * 4
    assert tick_step(100, 4, 600) < tick_step(100, 1, 600)
    assert format_time(61.25) == "01:01.25"
    panel.set_mode("audio")
    assert strip.cuts("audio") == ()
    assert strip.add_cut(35.5)
    panel.set_mode("split")
    assert len(strip.cuts("split")) == 1
    strip.clear_marks()
    assert strip.cuts("split") == ()
    panel.set_mode("trim")
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton,
                     pos=QPoint(round(strip.x_for_time(12.5)), 50))
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton,
                     pos=QPoint(round(strip.x_for_time(31.25)), 50))
    assert strip.trim_start == pytest.approx(12.5, abs=0.1)
    assert strip.trim_end == pytest.approx(31.25, abs=0.1)
    panel.close()
    panel.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_timeline_modes_drive_commands_and_fit_window(
    tmp_path: Path, qt_app: QApplication
) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(SettingsService(backend), HistoryService(tmp_path / "history.json"))
    source = tmp_path / "时间轴 视频.mp4"
    source.touch()
    window._show_media(MediaInfo(
        source, 125.0, "mp4", (MediaStream(0, "video", "h264", 1920, 1080),
                               MediaStream(1, "audio", "aac", channels=2)),
    ))
    window.show()
    qt_app.processEvents()
    assert window.height() == 850
    assert window.height() <= 1024
    assert window.maximumHeight() > 1024
    assert window.timeline.height() == 260
    assert window.tabs.geometry().top() - window.brand.geometry().bottom() <= 12
    assert window.timeline.strip.TRACK_HEIGHT >= window.brand.height() * 0.8
    assert window.source_info.mapTo(window, QPoint(0, 0)).y() < (
        window.source_path.mapTo(window, QPoint(0, 0)).y()
    )
    assert window.source_info.parentWidget().height() <= 90
    assert window.page_scroll.horizontalScrollBar().maximum() == 0
    window.tabs.setCurrentIndex(2)
    assert window.timeline.strip.add_cut(20.5)
    assert window.timeline.strip.add_cut(61.25)
    assert window.split_mode.currentData() == "cuts"
    window._add_jobs("split")
    assert [job.duration_seconds for job in window._jobs] == [20.5, 40.75, 63.75]
    window.tabs.setCurrentIndex(4)
    assert window.page_scroll.verticalScrollBar().maximum() == 0
    audio_form = window.pages.widget(4).layout().itemAt(1).layout()
    audio_grid = audio_form.itemAt(0).widget().layout()
    assert [audio_grid.itemAtPosition(0, i).widget() is not None for i in range(4)] == [True] * 4
    assert [audio_grid.itemAtPosition(1, i) is not None for i in range(4)] == (
        [True, True, True, False]
    )
    assert max(audio_grid.itemAtPosition(0, i).widget().width() for i in range(4)) - min(
        audio_grid.itemAtPosition(1, i).widget().width() for i in range(3)
    ) <= 2
    audio_heading = window.pages.widget(4).layout().itemAt(0).layout()
    assert audio_heading.itemAt(0).widget().geometry().top() == (
        audio_heading.itemAt(2).widget().geometry().top()
    )
    assert window.timeline.strip.cuts("audio") == ()
    assert window.timeline.strip.add_cut(50.25)
    assert window.audio_mode.currentData() == "cuts"
    window._add_jobs("audio")
    assert [job.duration_seconds for job in window._jobs[-2:]] == [50.25, 74.75]
    window.tabs.setCurrentIndex(3)
    trim_form = window.pages.widget(3).layout().itemAt(1).layout()
    trim_grid = trim_form.itemAt(0).widget().layout()
    assert trim_grid.itemAtPosition(1, 3) is None
    assert [trim_grid.itemAtPosition(1, i).widget().width() for i in range(3)] == [
        trim_grid.itemAtPosition(0, i).widget().width() for i in range(3)
    ]
    assert window.page_scroll.horizontalScrollBar().maximum() == 0
    window.timeline.strip.set_trim_range(12.5, 31.25, emit=True)
    assert window.trim_start.value() == 12.5
    assert window.trim_end.value() == 31.25
    window._add_jobs("trim")
    assert window._jobs[-1].duration_seconds == 18.75
    assert window._jobs[-1].command[window._jobs[-1].command.index("-ss") + 1] == "12.500"
    window.trim_start.setValue(14.25)
    assert window.timeline.strip.trim_start == 14.25
    window.showMaximized()
    qt_app.processEvents()
    assert window.isMaximized()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_source_media_thumbnail_worker(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[1]
    ffmpeg = root / "source" / "ffmpeg" / "bin" / "ffmpeg.exe"
    sources = list((root / "source").glob("*.mp4"))
    if not ffmpeg.is_file() or not sources:
        pytest.skip("本地 FFmpeg 或 source 视频不可用")
    launch_flags: list[int] = []
    original_popen = subprocess.Popen

    def launch(*args, **kwargs):
        launch_flags.append(kwargs.get("creationflags", -1))
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", launch)
    results: list[tuple[int, bytes]] = []
    worker = ThumbnailWorker(ffmpeg, sources[0], 1.0, count=3)
    worker.frame_ready.connect(lambda _source, index, data: results.append((index, data)))
    worker.start()
    assert worker.wait(40000)
    qt_app.processEvents()
    assert len(results) == 3
    assert all(not QImage.fromData(data).isNull() for _, data in results)
    assert launch_flags == [MEDIA_PROCESS_CREATION_FLAGS] * 3
    assert MEDIA_PROCESS_CREATION_FLAGS == getattr(subprocess, "CREATE_NO_WINDOW", 0)
