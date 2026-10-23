"""FFprobe JSON parsing and media metadata access."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ffmpeg_studio.core.ffmpeg import MEDIA_PROCESS_CREATION_FLAGS, FfmpegError


@dataclass(frozen=True, slots=True)
class MediaStream:
    index: int
    codec_type: str
    codec_name: str | None
    width: int | None = None
    height: int | None = None
    channels: int | None = None


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: Path
    duration_seconds: float | None
    format_name: str | None
    streams: tuple[MediaStream, ...]


def parse_probe_payload(source_file: Path, payload: dict[str, Any]) -> MediaInfo:
    """Convert ffprobe's JSON document into a compact, typed media model."""
    format_data = payload.get("format", {})
    raw_duration = format_data.get("duration")
    try:
        duration = float(raw_duration) if raw_duration is not None else None
    except (TypeError, ValueError):
        duration = None

    streams = tuple(
        MediaStream(
            index=int(stream.get("index", 0)),
            codec_type=str(stream.get("codec_type", "unknown")),
            codec_name=stream.get("codec_name"),
            width=_positive_int(stream.get("width")),
            height=_positive_int(stream.get("height")),
            channels=_positive_int(stream.get("channels")),
        )
        for stream in payload.get("streams", [])
    )
    return MediaInfo(
        path=source_file,
        duration_seconds=duration,
        format_name=format_data.get("format_name"),
        streams=streams,
    )


def probe_media(ffprobe_path: Path, source_file: Path, timeout_seconds: float = 10.0) -> MediaInfo:
    """Read a local media file with ffprobe and return metadata."""
    arguments = [
        str(ffprobe_path),
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(source_file),
    ]
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=MEDIA_PROCESS_CREATION_FLAGS,
        )
    except OSError as error:
        raise FfmpegError(f"无法启动 ffprobe: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise FfmpegError(f"分析媒体超时: {source_file}") from error

    if result.returncode != 0:
        raise FfmpegError(result.stderr.strip() or f"无法分析媒体: {source_file}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise FfmpegError("ffprobe 返回了无效的 JSON 数据") from error
    return parse_probe_payload(source_file, payload)


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
