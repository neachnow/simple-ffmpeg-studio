from pathlib import Path

from PySide6.QtCore import QSettings

from ffmpeg_studio.services.settings import (
    DEFAULT_OUTPUT_FOLDER_NAME,
    AppSettings,
    SettingsService,
)


def test_settings_round_trip() -> None:
    backend = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test-org", "test-app")
    backend.clear()
    service = SettingsService(backend)

    service.save(
        AppSettings(
            ffmpeg_path="C:/tools/ffmpeg.exe",
            ffprobe_path="C:/tools/ffprobe.exe",
            default_output_directory="C:/exports",
            max_concurrent_jobs=2,
        )
    )

    assert service.load() == AppSettings(
        ffmpeg_path="C:/tools/ffmpeg.exe",
        ffprobe_path="C:/tools/ffprobe.exe",
        default_output_directory="C:/exports",
        max_concurrent_jobs=2,
    )


def test_concurrency_is_constrained() -> None:
    backend = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "test-org", "limit-app")
    backend.clear()
    service = SettingsService(backend)

    service.save(AppSettings(max_concurrent_jobs=99))

    assert service.load().max_concurrent_jobs == 2


def test_suggested_output_directory_is_next_to_source() -> None:
    source = Path("C:/视频/源文件.mp4")

    assert SettingsService.suggested_output_directory(source) == source.parent / DEFAULT_OUTPUT_FOLDER_NAME
