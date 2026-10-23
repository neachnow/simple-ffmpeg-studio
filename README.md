# FFmpeg Studio

一个基于 Python 与 PySide6 Essentials 的本地 FFmpeg 图形化工作台。

当前处于 MVP 开发阶段。产品范围与开发里程碑请见 [PRD](docs/PRD.md)。

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ffmpeg-studio
```

应用本身不捆绑 FFmpeg。后续版本会在“设置”中提供 FFmpeg 与 FFprobe 路径配置。
