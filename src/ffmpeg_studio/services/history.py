"""Small local record of finished FFmpeg tasks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    finished_at: str
    label: str
    output: str
    state: str
    returncode: int


class HistoryService:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            app_data = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
            path = Path(app_data) / "history.json"
        self.path = path

    def load(self) -> list[HistoryRecord]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [HistoryRecord(**item) for item in data[:100]]
        except (OSError, ValueError, TypeError, KeyError):
            return []

    def add(self, label: str, output: Path, state: str, returncode: int) -> None:
        record = HistoryRecord(
            finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            label=label,
            output=str(output),
            state=state,
            returncode=returncode,
        )
        records = [record, *self.load()][:100]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(item) for item in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        if self.path.is_file():
            self.path.unlink()
