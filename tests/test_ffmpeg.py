import subprocess
from pathlib import Path

import pytest

from ffmpeg_studio.core.ffmpeg import (
    FfmpegError,
    TranscodeRequest,
    build_transcode_command,
    cancel_process,
    format_command,
    inspect_executable,
    parse_progress_line,
    parse_timestamp,
)
from ffmpeg_studio.core.probe import parse_probe_payload


def test_parses_ffmpeg_timestamp() -> None:
    assert parse_timestamp("01:02:03.50") == 3723.5


def test_parses_progress_and_clamps_percentage() -> None:
    progress = parse_progress_line("frame= 42 fps=10 time=00:00:12.50 speed=1.25x", 10)

    assert progress is not None
    assert progress.processed_seconds == 12.5
    assert progress.speed == 1.25
    assert progress.percent == 100.0


def test_ignores_non_progress_lines() -> None:
    assert parse_progress_line("Input #0, mov,mp4", 10) is None


def test_builds_non_overwriting_command_with_unicode_paths() -> None:
    command = build_transcode_command(
        Path("C:/工具/ffmpeg.exe"),
        TranscodeRequest(
            source=Path("C:/素材/一段 视频.mp4"),
            output=Path("C:/输出/处理后 视频.mp4"),
        ),
    )

    assert command[0] == str(Path("C:/工具/ffmpeg.exe"))
    assert command[1:5] == ("-hide_banner", "-n", "-i", str(Path("C:/素材/一段 视频.mp4")))
    assert command[-1] == str(Path("C:/输出/处理后 视频.mp4"))
    assert "视频.mp4" in format_command(command)


def test_parses_probe_payload() -> None:
    media = parse_probe_payload(
        Path("C:/素材/测试.mp4"),
        {
            "format": {"duration": "12.25", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
            "streams": [
                {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2},
            ],
        },
    )

    assert media.duration_seconds == 12.25
    assert media.streams[0].width == 1920
    assert media.streams[1].channels == 2


def test_invalid_probe_duration_is_tolerated() -> None:
    media = parse_probe_payload(Path("broken.mp4"), {"format": {"duration": "not-a-number"}})

    assert media.duration_seconds is None


def test_inspect_reports_failed_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "not ffmpeg"),
    )

    with pytest.raises(FfmpegError, match="not ffmpeg"):
        inspect_executable(Path("C:/tools/ffmpeg.exe"))


class _SlowProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.wait_count = 0

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> None:
        self.wait_count += 1
        if self.wait_count == 1:
            raise subprocess.TimeoutExpired("ffmpeg", timeout)

    def kill(self) -> None:
        self.killed = True


def test_cancel_force_kills_after_timeout() -> None:
    process = _SlowProcess()

    cancel_process(process)  # type: ignore[arg-type]

    assert process.terminated is True
    assert process.killed is True
