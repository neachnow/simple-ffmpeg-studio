"""Turn form values into safe, non-overwriting FFmpeg jobs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ffmpeg_studio.core.ffmpeg import TranscodeRequest, build_transcode_command


@dataclass(frozen=True, slots=True)
class PlannedJob:
    label: str
    output: Path
    command: tuple[str, ...]
    duration_seconds: float | None


_AUDIO_CODECS = {
    "mp3": ("libmp3lame", "192k"),
    "aac": ("aac", "192k"),
    "wav": ("pcm_s16le", None),
    "flac": ("flac", None),
}


def unique_output(folder: Path, stem: str, extension: str, reserved: set[Path]) -> Path:
    """Choose a free path without creating or overwriting a file."""
    candidate = folder / f"{stem}.{extension}"
    suffix = 2
    while candidate.exists() or candidate in reserved:
        candidate = folder / f"{stem} ({suffix}).{extension}"
        suffix += 1
    reserved.add(candidate)
    return candidate


def plan_jobs(
    operation: str,
    ffmpeg: Path,
    source: Path,
    output_folder: Path,
    duration_seconds: float | None,
    *,
    segment_seconds: int | None = None,
    audio_format: str = "mp3",
    quality: int = 23,
    reserved: set[Path] | None = None,
) -> list[PlannedJob]:
    """Plan transcode, video split, or audio extraction from one source.

    A requested segment length creates one numbered output per interval. The final
    interval is capped at the source duration. Every output is allocated uniquely.
    """
    if not source.is_file():
        raise ValueError("请先选择有效的源视频文件")
    if operation not in {"transcode", "split", "audio"}:
        raise ValueError("未知处理功能")
    if not 0 <= quality <= 51:
        raise ValueError("质量参数 CRF 必须在 0 到 51 之间")
    if operation == "audio" and audio_format not in _AUDIO_CODECS:
        raise ValueError("不支持的音频格式")
    if segment_seconds is not None:
        if segment_seconds <= 0:
            raise ValueError("分段时长必须大于 0 秒")
        if duration_seconds is None or duration_seconds <= 0:
            raise ValueError("无法读取视频时长，不能按时长分段")
        if math.ceil(duration_seconds / segment_seconds) > 500:
            raise ValueError("分段数量超过 500，请增大每段时长")

    occupied = reserved if reserved is not None else set()
    segments = (
        [(i * segment_seconds, min(segment_seconds, duration_seconds - i * segment_seconds))
         for i in range(math.ceil(duration_seconds / segment_seconds))]
        if segment_seconds is not None else [(0, duration_seconds)]
    )
    jobs: list[PlannedJob] = []
    for index, (start, length) in enumerate(segments, 1):
        stem = source.stem + (f"_{index:03d}" if segment_seconds is not None else "")
        tag = {"transcode": "转码", "split": "分割", "audio": "音频"}[operation]
        if operation == "transcode":
            output = unique_output(output_folder, stem + "_transcoded", "mp4", occupied)
            command = build_transcode_command(
                ffmpeg, TranscodeRequest(source, output, quality=quality)
            )
        elif operation == "split":
            output = unique_output(output_folder, stem + "_video", "mp4", occupied)
            command_parts = [str(ffmpeg), "-hide_banner", "-nostdin", "-n"]
            if segment_seconds is not None:
                command_parts += ["-ss", f"{start:.3f}"]
            command_parts += ["-i", str(source)]
            if segment_seconds is not None:
                command_parts += ["-t", f"{length:.3f}"]
            command_parts += [
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                "-crf", str(quality), "-c:a", "aac", str(output),
            ]
            command = tuple(command_parts)
        else:
            codec, bitrate = _AUDIO_CODECS[audio_format]
            output = unique_output(output_folder, stem + "_audio", audio_format, occupied)
            command_parts = [str(ffmpeg), "-hide_banner", "-nostdin", "-n"]
            if segment_seconds is not None:
                command_parts += ["-ss", f"{start:.3f}"]
            command_parts += ["-i", str(source)]
            if segment_seconds is not None:
                command_parts += ["-t", f"{length:.3f}"]
            command_parts += ["-vn", "-map", "0:a:0", "-c:a", codec]
            if bitrate is not None:
                command_parts += ["-b:a", bitrate]
            command = tuple([*command_parts, str(output)])
        jobs.append(PlannedJob(f"{tag} · {index}/{len(segments)}" if len(segments) > 1 else tag,
                               output, command, length))
    return jobs
