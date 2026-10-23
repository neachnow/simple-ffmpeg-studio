"""Safe FFmpeg process discovery, execution, and progress parsing."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_TIME_PATTERN = re.compile(r"\btime=(?P<value>\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
_SPEED_PATTERN = re.compile(r"\bspeed=\s*(?P<value>[\d.]+)x")
MEDIA_PROCESS_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True, slots=True)
class ExecutableInfo:
    path: Path
    version: str


@dataclass(frozen=True, slots=True)
class FfmpegProgress:
    processed_seconds: float
    speed: float | None
    percent: float | None


@dataclass(frozen=True, slots=True)
class TranscodeRequest:
    """Validated, minimal settings for a single transcode operation."""

    source: Path
    output: Path
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    quality: int | None = 23


def build_transcode_command(ffmpeg_path: Path, request: TranscodeRequest) -> tuple[str, ...]:
    """Build an argv tuple for a safe, non-overwriting H.264/AAC transcode."""
    command = [
        str(ffmpeg_path),
        "-hide_banner",
        "-n",
        "-i",
        str(request.source),
        "-c:v",
        request.video_codec,
        "-c:a",
        request.audio_codec,
    ]
    if request.quality is not None:
        command.extend(("-crf", str(request.quality)))
    command.append(str(request.output))
    return tuple(command)


def format_command(arguments: Sequence[str]) -> str:
    """Format argv for display only; the result must never be sent to a shell."""
    return subprocess.list2cmdline(list(arguments))


class FfmpegError(RuntimeError):
    """Raised when an FFmpeg executable cannot be inspected or invoked."""


def find_executable(preferred_path: str | Path | None, command_name: str) -> Path | None:
    """Find an executable from settings first, then on PATH."""
    if preferred_path:
        candidate = Path(preferred_path).expanduser()
        if candidate.is_file():
            return candidate

    located = shutil.which(command_name)
    return Path(located) if located else None


def inspect_executable(executable: Path, timeout_seconds: float = 5.0) -> ExecutableInfo:
    """Return the first FFmpeg version line, raising an actionable error on failure."""
    try:
        result = subprocess.run(
            [str(executable), "-version"],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=MEDIA_PROCESS_CREATION_FLAGS,
        )
    except OSError as error:
        raise FfmpegError(f"无法启动 {executable}: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise FfmpegError(f"检测 {executable} 超时") from error

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise FfmpegError(f"{executable} 不可用: {message}")

    version_line = next((line for line in result.stdout.splitlines() if line.strip()), "未知版本")
    return ExecutableInfo(path=executable, version=version_line)


def parse_timestamp(value: str) -> float:
    """Convert the FFmpeg ``HH:MM:SS.fraction`` value to seconds."""
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_progress_line(line: str, duration_seconds: float | None) -> FfmpegProgress | None:
    """Parse a normal FFmpeg status line into progress data."""
    time_match = _TIME_PATTERN.search(line)
    if time_match is None:
        return None

    processed_seconds = parse_timestamp(time_match.group("value"))
    speed_match = _SPEED_PATTERN.search(line)
    speed = float(speed_match.group("value")) if speed_match else None
    percent = None
    if duration_seconds and duration_seconds > 0:
        percent = max(0.0, min(processed_seconds / duration_seconds * 100, 100.0))
    return FfmpegProgress(processed_seconds=processed_seconds, speed=speed, percent=percent)


def start_process(arguments: Sequence[str]) -> subprocess.Popen[str]:
    """Start FFmpeg without a shell so paths and user values stay data, not commands."""
    if not arguments:
        raise ValueError("FFmpeg 参数不能为空")
    try:
        return subprocess.Popen(
            list(arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=MEDIA_PROCESS_CREATION_FLAGS,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise FfmpegError(f"无法启动 {arguments[0]}: {error}") from error


def cancel_process(process: subprocess.Popen[str], timeout_seconds: float = 3.0) -> None:
    """Terminate a running FFmpeg process, force-killing only if it does not exit."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
