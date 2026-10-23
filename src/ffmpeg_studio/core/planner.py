"""Turn form values into safe, non-overwriting FFmpeg jobs."""

from __future__ import annotations

import math
from collections.abc import Sequence
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
_ROTATIONS = {
    "none": None,
    "clockwise": "transpose=1",
    "counterclockwise": "transpose=2",
    "flip_horizontal": "hflip",
    "flip_vertical": "vflip",
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
    cut_points: Sequence[float] | None = None,
    audio_format: str = "mp3",
    quality: int = 23,
    start_seconds: int = 0,
    end_seconds: int | None = None,
    rotation: str = "none",
    crop: tuple[int, int, int, int] | None = None,
    video_size: tuple[int, int] | None = None,
    audio_bitrate: str = "192k",
    sample_rate: int | None = None,
    channels: int | None = None,
    gain_db: int = 0,
    reserved: set[Path] | None = None,
) -> list[PlannedJob]:
    """Plan transcode, video split, or audio extraction from one source.

    A requested segment length creates one numbered output per interval. The final
    interval is capped at the source duration. Every output is allocated uniquely.
    """
    if not source.is_file():
        raise ValueError("请先选择有效的源视频文件")
    if operation not in {"transcode", "split", "audio", "trim"}:
        raise ValueError("未知处理功能")
    if not 0 <= quality <= 51:
        raise ValueError("质量参数 CRF 必须在 0 到 51 之间")
    if operation == "audio" and audio_format not in _AUDIO_CODECS:
        raise ValueError("不支持的音频格式")
    if audio_bitrate not in {"128k", "192k", "256k", "320k"}:
        raise ValueError("不支持的音频码率")
    if sample_rate not in {None, 44100, 48000}:
        raise ValueError("不支持的采样率")
    if channels not in {None, 1, 2}:
        raise ValueError("声道数只能是 1 或 2")
    if not -12 <= gain_db <= 12:
        raise ValueError("音量增益必须在 -12 到 12 dB 之间")
    if rotation not in _ROTATIONS:
        raise ValueError("不支持的旋转或翻转选项")
    if operation == "trim":
        if duration_seconds is None or duration_seconds <= 0:
            raise ValueError("无法读取视频时长，不能裁剪")
        if start_seconds < 0 or start_seconds >= duration_seconds:
            raise ValueError("开始时间必须在视频时长范围内")
        if end_seconds is not None and (end_seconds <= start_seconds
                                        or end_seconds > duration_seconds):
            raise ValueError("结束时间必须晚于开始时间且不超过视频时长")
        if crop is not None:
            width, height, x, y = crop
            if video_size is None or min(width, height) <= 0 or min(x, y) < 0:
                raise ValueError("裁切区域参数无效")
            if x + width > video_size[0] or y + height > video_size[1]:
                raise ValueError("裁切区域超出原视频画面")
    if segment_seconds is not None and cut_points is not None:
        raise ValueError("固定时长分段和时间轴切点不能同时使用")
    if cut_points is not None:
        if operation not in {"split", "audio"}:
            raise ValueError("当前功能不支持时间轴多切点")
        if duration_seconds is None or duration_seconds <= 0:
            raise ValueError("无法读取视频时长，不能使用时间轴切点")
        if not cut_points:
            raise ValueError("请先在时间轴上添加至少一个切点")
        if len(cut_points) > 499:
            raise ValueError("切点数量超过 499")
        if any(not math.isfinite(point) or not 0 < point < duration_seconds
               for point in cut_points):
            raise ValueError("切点必须位于视频时长范围内")
        ordered_cuts = sorted(round(point, 3) for point in cut_points)
        if ordered_cuts[0] < 0.01 or duration_seconds - ordered_cuts[-1] < 0.01:
            raise ValueError("切点与视频首尾至少相隔 0.01 秒")
        if any(right - left < 0.01 for left, right in zip(ordered_cuts, ordered_cuts[1:])):
            raise ValueError("切点之间至少相隔 0.01 秒")
    if segment_seconds is not None:
        if segment_seconds <= 0:
            raise ValueError("分段时长必须大于 0 秒")
        if duration_seconds is None or duration_seconds <= 0:
            raise ValueError("无法读取视频时长，不能按时长分段")
        if math.ceil(duration_seconds / segment_seconds) > 500:
            raise ValueError("分段数量超过 500，请增大每段时长")

    occupied = reserved if reserved is not None else set()
    segmented = segment_seconds is not None or cut_points is not None
    if cut_points is not None:
        boundaries = [0.0, *ordered_cuts, duration_seconds]
        segments = [
            (start, end - start)
            for start, end in zip(boundaries, boundaries[1:])
        ]
    elif segment_seconds is not None:
        segments = [
            (i * segment_seconds, min(segment_seconds, duration_seconds - i * segment_seconds))
            for i in range(math.ceil(duration_seconds / segment_seconds))
        ]
    else:
        segments = [(0, duration_seconds)]
    if operation == "trim":
        segments = [(start_seconds, (end_seconds or duration_seconds) - start_seconds)]
    jobs: list[PlannedJob] = []
    for index, (start, length) in enumerate(segments, 1):
        stem = source.stem + (f"_{index:03d}" if segmented else "")
        tag = {"transcode": "转码", "split": "分割", "audio": "音频", "trim": "裁剪"}[operation]
        if operation == "transcode":
            output = unique_output(output_folder, stem + "_transcoded", "mp4", occupied)
            command = build_transcode_command(
                ffmpeg, TranscodeRequest(source, output, quality=quality)
            )
        elif operation == "split":
            output = unique_output(output_folder, stem + "_video", "mp4", occupied)
            command_parts = [str(ffmpeg), "-hide_banner", "-nostdin", "-n"]
            if segmented:
                command_parts += ["-ss", f"{start:.3f}"]
            command_parts += ["-i", str(source)]
            if segmented:
                command_parts += ["-t", f"{length:.3f}"]
            command_parts += [
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
                "-crf", str(quality), "-c:a", "aac", str(output),
            ]
            command = tuple(command_parts)
        elif operation == "trim":
            output = unique_output(output_folder, stem + "_trimmed", "mp4", occupied)
            command_parts = [str(ffmpeg), "-hide_banner", "-nostdin", "-n",
                             "-ss", f"{start:.3f}", "-i", str(source),
                             "-t", f"{length:.3f}", "-map", "0:v:0", "-map", "0:a?"]
            filters = []
            if crop is not None:
                width, height, x, y = crop
                filters.append(f"crop={width}:{height}:{x}:{y}")
            if _ROTATIONS[rotation]:
                filters.append(_ROTATIONS[rotation])
            if filters:
                command_parts += ["-vf", ",".join(filters)]
            command_parts += ["-c:v", "libx264", "-crf", str(quality),
                              "-c:a", "aac", str(output)]
            command = tuple(command_parts)
        else:
            codec, _ = _AUDIO_CODECS[audio_format]
            output = unique_output(output_folder, stem + "_audio", audio_format, occupied)
            command_parts = [str(ffmpeg), "-hide_banner", "-nostdin", "-n"]
            if segmented:
                command_parts += ["-ss", f"{start:.3f}"]
            command_parts += ["-i", str(source)]
            if segmented:
                command_parts += ["-t", f"{length:.3f}"]
            command_parts += ["-vn", "-map", "0:a:0", "-c:a", codec]
            if audio_format in {"mp3", "aac"}:
                command_parts += ["-b:a", audio_bitrate]
            if sample_rate is not None:
                command_parts += ["-ar", str(sample_rate)]
            if channels is not None:
                command_parts += ["-ac", str(channels)]
            if gain_db:
                command_parts += ["-af", f"volume={gain_db}dB"]
            command = tuple([*command_parts, str(output)])
        jobs.append(PlannedJob(f"{tag} · {index}/{len(segments)}" if len(segments) > 1 else tag,
                               output, command, length))
    return jobs
