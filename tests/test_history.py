"""Local task history behavior."""

from pathlib import Path

from ffmpeg_studio.services.history import HistoryService


def test_history_persists_unicode_paths_and_clear(tmp_path: Path) -> None:
    history = HistoryService(tmp_path / "settings" / "history.json")
    output = tmp_path / "处理 结果.mp3"
    history.add("提取音频", output, "已完成", 0)
    records = HistoryService(history.path).load()
    assert len(records) == 1
    assert records[0].output == str(output)
    assert records[0].label == "提取音频"
    history.clear()
    assert history.load() == []


def test_history_keeps_newest_hundred_and_ignores_corrupt_file(tmp_path: Path) -> None:
    history = HistoryService(tmp_path / "history.json")
    for number in range(105):
        history.add("转码", tmp_path / f"{number}.mp4", "已完成", 0)
    records = history.load()
    assert len(records) == 100
    assert records[0].output.endswith("104.mp4")
    assert records[-1].output.endswith("5.mp4")
    history.path.write_text("not JSON", encoding="utf-8")
    assert history.load() == []
