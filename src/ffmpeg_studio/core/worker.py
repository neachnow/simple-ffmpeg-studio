"""Execute one FFmpeg job on a background Qt thread."""

from __future__ import annotations

import subprocess
import threading

from PySide6.QtCore import QThread, Signal

from ffmpeg_studio.core.ffmpeg import MEDIA_PROCESS_CREATION_FLAGS, parse_progress_line
from ffmpeg_studio.core.planner import PlannedJob


class JobWorker(QThread):
    progress_changed = Signal(int, str)
    log_received = Signal(str)
    job_finished = Signal(str, int)

    def __init__(self, job: PlannedJob) -> None:
        super().__init__()
        self.job = job
        self._process: subprocess.Popen[str] | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def run(self) -> None:
        command = [*self.job.command[:-1], "-progress", "pipe:1", "-nostats", self.job.command[-1]]
        try:
            self.job.output.parent.mkdir(parents=True, exist_ok=True)
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                creationflags=MEDIA_PROCESS_CREATION_FLAGS,
            )
            self._process = process
            if self._cancelled:
                process.terminate()

            def drain_stderr() -> None:
                assert process.stderr is not None
                for line in process.stderr:
                    self.log_received.emit(line.rstrip())

            logger = threading.Thread(target=drain_stderr, daemon=True)
            logger.start()
            assert process.stdout is not None
            processed = 0.0
            for line in process.stdout:
                field, _, value = line.strip().partition("=")
                if field == "out_time":
                    progress = parse_progress_line("time=" + value, self.job.duration_seconds)
                    if progress is not None:
                        processed = progress.processed_seconds
                        percent = int(progress.percent or 0)
                        self.progress_changed.emit(percent, f"已处理 {processed:.1f} 秒")
            returncode = process.wait()
            logger.join()
            state = "已取消" if self._cancelled else ("已完成" if returncode == 0 else "失败")
            self.job_finished.emit(state, returncode)
        except OSError as error:
            self.log_received.emit(str(error))
            self.job_finished.emit("失败", -1)
