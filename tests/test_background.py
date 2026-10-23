"""User-selected appearance images remain optional and reversible."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSettings
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QMessageBox

from ffmpeg_studio.services.history import HistoryService
from ffmpeg_studio.services.settings import AppSettings, SettingsService
from ffmpeg_studio.ui.workspace import MainWindow


def _solid_image(path: Path) -> None:
    image = QImage(320, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("#336b42"))
    assert image.save(str(path))


def test_background_can_replace_window_or_banner_and_be_cleared(
    tmp_path: Path, qt_app: QApplication
) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    service = SettingsService(backend)
    picture = tmp_path / "背景 图.png"
    _solid_image(picture)
    window = MainWindow(service, HistoryService(tmp_path / "history.json"))
    window.show()
    qt_app.processEvents()
    default_corner = window.grab().toImage().pixelColor(8, 400)
    status_card = window.state_label.parentWidget()
    panel_point = status_card.mapTo(
        window, QPoint(status_card.width() - 30, status_card.height() - 10)
    )
    default_panel = window.grab().toImage().pixelColor(panel_point)
    input_point = window.source_path.mapTo(
        window, QPoint(window.source_path.width() - 20, window.source_path.height() // 2)
    )
    default_input = window.grab().toImage().pixelColor(input_point)
    original_banner = window.brand.pixmap().toImage().pixelColor(10, 10)
    banner_height = window.brand.height()

    window.background_input.setText(str(picture))
    window.background_target.setCurrentIndex(window.background_target.findData("window"))
    window._save_settings()
    qt_app.processEvents()
    assert service.load().background_image_path == str(picture)
    assert service.load().background_image_target == "window"
    assert not window.background_canvas.picture.isNull()
    assert window.grab().toImage().pixelColor(8, 400) != default_corner
    assert status_card.property("customBackground") is True
    assert isinstance(window.timeline.hint.graphicsEffect(), QGraphicsDropShadowEffect)
    assert window.grab().toImage().pixelColor(panel_point) != default_panel
    custom_input = window.grab().toImage().pixelColor(input_point)
    assert custom_input != default_input
    assert custom_input.green() > custom_input.red() + 12
    lower_card = window.pages.currentWidget()
    lower_point = lower_card.mapTo(window, QPoint(10, min(110, lower_card.height() - 10)))
    lower_color = window.grab().toImage().pixelColor(lower_point)
    assert lower_color.green() > lower_color.red() + 12

    window.background_target.setCurrentIndex(window.background_target.findData("banner"))
    window._save_settings()
    qt_app.processEvents()
    assert window.background_canvas.picture.isNull()
    assert status_card.property("customBackground") is False
    assert window.timeline.hint.graphicsEffect() is None
    assert window.brand.height() == banner_height
    assert window.brand.pixmap().toImage().pixelColor(10, 10) != original_banner
    assert service.load().background_image_target == "banner"
    reopened = MainWindow(service, HistoryService(tmp_path / "reopened-history.json"))
    reopened.show()
    qt_app.processEvents()
    assert reopened.background_canvas.picture.isNull()
    assert reopened.brand.pixmap().toImage().pixelColor(10, 10) != original_banner
    reopened.close()
    reopened.deleteLater()

    window.tabs.setCurrentIndex(5)
    qt_app.processEvents()
    assert window.page_scroll.horizontalScrollBar().maximum() == 0

    window._clear_background()
    qt_app.processEvents()
    assert service.load().background_image_path == ""
    assert window.background_canvas.picture.isNull()
    assert window.brand.pixmap().toImage().pixelColor(10, 10) == original_banner
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_invalid_or_missing_background_falls_back(
    tmp_path: Path, qt_app: QApplication, monkeypatch
) -> None:
    backend = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    service = SettingsService(backend)
    missing = tmp_path / "missing.png"
    service.save(AppSettings(background_image_path=str(missing)))
    window = MainWindow(service, HistoryService(tmp_path / "history.json"))
    window.show()
    qt_app.processEvents()
    assert window.background_canvas.picture.isNull()
    assert "不可用" in window.background_status.text()
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append("invalid"))
    window._save_settings()
    assert warnings == ["invalid"]
    assert service.load().background_image_path == str(missing)
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
