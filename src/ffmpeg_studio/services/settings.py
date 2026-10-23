"""Typed wrapper around persistent application settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

DEFAULT_OUTPUT_FOLDER_NAME = "FFmpeg Studio Output"
MAX_CONCURRENT_JOBS = 2


@dataclass(frozen=True, slots=True)
class AppSettings:
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    default_output_directory: str = ""
    max_concurrent_jobs: int = 1


class SettingsService:
    """Read and write the small, user-owned set of app preferences."""

    def __init__(self, backend: QSettings | None = None) -> None:
        self._backend = backend or QSettings()

    def load(self) -> AppSettings:
        max_jobs = self._backend.value("processing/max_concurrent_jobs", 1, type=int)
        return AppSettings(
            ffmpeg_path=self._backend.value("ffmpeg/path", "", type=str),
            ffprobe_path=self._backend.value("ffprobe/path", "", type=str),
            default_output_directory=self._backend.value("output/default_directory", "", type=str),
            max_concurrent_jobs=max(1, min(max_jobs, MAX_CONCURRENT_JOBS)),
        )

    def save(self, settings: AppSettings) -> None:
        safe_jobs = max(1, min(settings.max_concurrent_jobs, MAX_CONCURRENT_JOBS))
        self._backend.setValue("ffmpeg/path", settings.ffmpeg_path)
        self._backend.setValue("ffprobe/path", settings.ffprobe_path)
        self._backend.setValue("output/default_directory", settings.default_output_directory)
        self._backend.setValue("processing/max_concurrent_jobs", safe_jobs)
        self._backend.sync()

    @staticmethod
    def suggested_output_directory(source_file: Path) -> Path:
        """Return the non-destructive default output folder for a source media file."""
        return source_file.parent / DEFAULT_OUTPUT_FOLDER_NAME
