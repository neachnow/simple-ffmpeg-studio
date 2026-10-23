import subprocess
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ffmpeg_studio.core.planner import plan_jobs
from ffmpeg_studio.core.worker import JobWorker


def test_split_and_audio_segments_use_requested_length(tmp_path: Path) -> None:
    source = tmp_path / "中文 source.mp4"
    source.touch()
    ffmpeg = Path("C:/tools/ffmpeg.exe")
    reserved: set[Path] = set()

    videos = plan_jobs("split", ffmpeg, source, tmp_path, 125, segment_seconds=60,
                       reserved=reserved)
    audios = plan_jobs("audio", ffmpeg, source, tmp_path, 125, segment_seconds=60,
                       audio_format="mp3", reserved=reserved)

    assert len(videos) == len(audios) == 3
    assert [job.duration_seconds for job in videos] == [60, 60, 5]
    assert videos[-1].command[videos[-1].command.index("-ss") + 1] == "120.000"
    assert audios[-1].command[audios[-1].command.index("-t") + 1] == "5.000"
    assert audios[0].output.suffix == ".mp3"
    assert "libmp3lame" in audios[0].command
    assert all(job.command[-1] == str(job.output) for job in [*videos, *audios])
    assert all("-n" in job.command for job in [*videos, *audios])


def test_full_length_and_collision_are_safe(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.touch()
    first = plan_jobs("audio", Path("ffmpeg"), source, tmp_path, 12)[0]
    first.output.touch()
    second = plan_jobs("audio", Path("ffmpeg"), source, tmp_path, 12)[0]

    assert "-ss" not in first.command and "-t" not in first.command
    assert second.output != first.output
    assert first.output == tmp_path / "video_audio.mp3"


def test_invalid_segment_duration_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.touch()
    with pytest.raises(ValueError, match="大于 0"):
        plan_jobs("split", Path("ffmpeg"), source, tmp_path, 100, segment_seconds=0)


def test_trim_and_audio_advanced_parameters(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.touch()
    trim = plan_jobs(
        "trim", Path("ffmpeg"), source, tmp_path, 125,
        start_seconds=10, end_seconds=30, rotation="clockwise",
        crop=(640, 480, 10, 20), video_size=(1920, 1080),
    )[0]
    audio = plan_jobs(
        "audio", Path("ffmpeg"), source, tmp_path, 125,
        audio_format="mp3", audio_bitrate="256k", sample_rate=44100,
        channels=1, gain_db=3,
    )[0]
    assert trim.duration_seconds == 20
    assert trim.command[trim.command.index("-vf") + 1] == "crop=640:480:10:20,transpose=1"
    assert trim.command[trim.command.index("-ss") + 1] == "10.000"
    assert audio.command[audio.command.index("-b:a") + 1] == "256k"
    assert audio.command[audio.command.index("-ar") + 1] == "44100"
    assert audio.command[audio.command.index("-ac") + 1] == "1"
    assert audio.command[audio.command.index("-af") + 1] == "volume=3dB"
    with pytest.raises(ValueError, match="超出"):
        plan_jobs("trim", Path("ffmpeg"), source, tmp_path, 125,
                  crop=(640, 480, 1500, 0), video_size=(1920, 1080))


def test_source_media_short_clip_executes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    ffmpeg = root / "source" / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffprobe = root / "source" / "ffmpeg" / "bin" / "ffprobe.exe"
    videos = list((root / "source").glob("*.mp4"))
    if not ffmpeg.is_file() or not ffprobe.is_file() or not videos:
        pytest.skip("本地 FFmpeg 或 source 视频不可用")

    jobs = plan_jobs("audio", ffmpeg, videos[0], tmp_path, 1,
                     segment_seconds=1, audio_format="mp3")
    result = subprocess.run(jobs[0].command, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-1000:]
    assert jobs[0].output.is_file() and jobs[0].output.stat().st_size > 0
    metadata = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1", str(jobs[0].output)],
        capture_output=True, timeout=10,
    )
    assert metadata.returncode == 0


def test_video_split_short_clip_executes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    ffmpeg = root / "source" / "ffmpeg" / "bin" / "ffmpeg.exe"
    sources = list((root / "source").glob("*.mp4"))
    if not ffmpeg.is_file() or not sources:
        pytest.skip("本地 FFmpeg 或 source 视频不可用")
    job = plan_jobs("split", ffmpeg, sources[0], tmp_path, 1, segment_seconds=1)[0]
    result = subprocess.run(job.command, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-1000:]
    assert job.output.stat().st_size > 0


def test_trim_transform_short_clip_executes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    ffmpeg = root / "source" / "ffmpeg" / "bin" / "ffmpeg.exe"
    sources = list((root / "source").glob("*.mp4"))
    if not ffmpeg.is_file() or not sources:
        pytest.skip("本地 FFmpeg 或 source 视频不可用")
    job = plan_jobs(
        "trim", ffmpeg, sources[0], tmp_path, 245.362,
        start_seconds=0, end_seconds=1, crop=(640, 480, 0, 0),
        video_size=(1920, 1160), rotation="clockwise",
    )[0]
    result = subprocess.run(job.command, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-1000:]
    assert job.output.stat().st_size > 0


def test_background_worker_reports_completion(tmp_path: Path, qt_app: QApplication) -> None:
    root = Path(__file__).resolve().parents[1]
    ffmpeg = root / "source" / "ffmpeg" / "bin" / "ffmpeg.exe"
    videos = list((root / "source").glob("*.mp4"))
    if not ffmpeg.is_file() or not videos:
        pytest.skip("本地 FFmpeg 或 source 视频不可用")
    job = plan_jobs("audio", ffmpeg, videos[0], tmp_path, 1,
                    segment_seconds=1, audio_format="mp3")[0]
    result: list[tuple[str, int]] = []
    worker = JobWorker(job)
    worker.job_finished.connect(lambda state, code: result.append((state, code)))
    worker.start()
    assert worker.wait(60000)
    qt_app.processEvents()
    assert result == [("已完成", 0)]
    assert job.output.stat().st_size > 0
