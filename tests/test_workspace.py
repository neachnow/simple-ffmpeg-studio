import subprocess
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication, QInputDialog

from ffmpeg_studio.core.probe import MediaInfo, MediaStream, probe_media
from ffmpeg_studio.services.history import HistoryService
from ffmpeg_studio.services.settings import SettingsService
from ffmpeg_studio.ui.workspace import MainWindow


def test_tabs_keep_source_and_status_visible(tmp_path: Path, qt_app: QApplication) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(SettingsService(backend), HistoryService(tmp_path / "history.json"))
    assert not window.brand.pixmap().isNull()
    assert not window.windowIcon().isNull()
    assert window.brand.pixmap().width() <= window.width() - 72
    assert window.tabs.tabText(1) == "转码 / Transcode"
    assert window.tabs.tabText(4) == "提取音频 / Extract Audio"
    source = tmp_path / "test.mp4"
    source.touch()
    window._media = MediaInfo(
        source, 125.0, "mp4", (MediaStream(0, "video", "h264", 1920, 1080),
                              MediaStream(1, "audio", "aac", channels=2)),
    )
    window._show_media(window._media)
    window.tabs.setCurrentIndex(2)
    window.split_mode.setCurrentIndex(1)
    window.split_seconds.setValue(60)
    window._add_jobs("split")
    assert window.queue.count() == 3
    assert "1920×1080" in window.source_info.text()
    window.tabs.setCurrentIndex(4)
    assert window.pages.currentIndex() == 4
    assert window.queue.count() == 3
    assert window.audio_format.currentData() == "mp3"
    window.tabs.setCurrentIndex(3)
    window.trim_start.setValue(10)
    window.trim_end.setValue(20)
    window.trim_rotation.setCurrentIndex(1)
    window.crop_width.setValue(640)
    window.crop_height.setValue(480)
    window._add_jobs("trim")
    assert window.queue.count() == 4
    assert "crop=640:480:0:0,transpose=1" in window.command_preview.toPlainText()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_ui_transcode_short_source_video(tmp_path: Path, qt_app: QApplication) -> None:
    root = Path(__file__).resolve().parents[1]
    ffmpeg = root / "source" / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffprobe = root / "source" / "ffmpeg" / "bin" / "ffprobe.exe"
    sources = list((root / "source").glob("*.mp4"))
    if not ffmpeg.is_file() or not ffprobe.is_file() or not sources:
        pytest.skip("本地 FFmpeg 或 source 视频不可用")
    clip = tmp_path / "测试 片段.mp4"
    prepare = subprocess.run(
        [str(ffmpeg), "-v", "error", "-n", "-t", "1", "-i", str(sources[0]),
         "-c", "copy", str(clip)], capture_output=True, timeout=30,
    )
    assert prepare.returncode == 0
    backend = QSettings(str(tmp_path / "ui-settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(SettingsService(backend), HistoryService(tmp_path / "history.json"))
    window._show_media(probe_media(ffprobe, clip))
    window.tabs.setCurrentIndex(1)
    window._add_jobs("transcode")
    assert window.queue.count() == 1
    window._start_next()
    deadline = time.monotonic() + 60
    while window._states[0] == "运行中" and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    qt_app.processEvents()
    assert window._states == ["已完成"], window.log_view.toPlainText()[-1200:]
    assert window._jobs[0].output.is_file()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_queue_edit_reorder_remove_retry_and_history(
    tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = QSettings(str(tmp_path / "queue.ini"), QSettings.Format.IniFormat)
    history = HistoryService(tmp_path / "history.json")
    window = MainWindow(SettingsService(backend), history)
    source = tmp_path / "队列 源.mp4"
    source.touch()
    window._show_media(MediaInfo(source, 120.0, "mp4", (MediaStream(0, "video", "h264"),)))
    window.split_mode.setCurrentIndex(1)
    window.split_seconds.setValue(60)
    window._add_jobs("split")
    assert window.queue.count() == 2
    first_output = window._jobs[0].output
    window.queue.setCurrentRow(0)
    edited_output = tmp_path / "新输出.mp4"
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: (str(edited_output), True))
    window._edit_selected_output()
    assert window._jobs[0].output == edited_output
    assert window._jobs[0].command[-1] == str(edited_output)
    assert first_output not in window._reserved
    window._move_selected(1)
    assert window._jobs[1].output == edited_output
    window._remove_selected()
    assert window.queue.count() == 1
    assert edited_output not in window._reserved
    window.queue.setCurrentRow(0)
    window._states[0] = "失败"
    window._refresh_queue()
    window._retry_selected()
    assert window.queue.count() == 2
    assert window._states[-1] == "等待中"
    assert window._jobs[-1].output != window._jobs[0].output
    window._active_index = 0
    monkeypatch.setattr(window, "_start_next", lambda: None)
    window._on_job_finished("失败", 1)
    assert history.load()[0].state == "失败"
    assert window.history_list.count() == 1
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
