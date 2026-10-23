# FFmpeg Studio

一个基于 Python 与 PySide6 Essentials 的本地 FFmpeg 图形化工作台。

当前处于 MVP 开发阶段。产品范围与开发里程碑请见 [PRD](docs/PRD.md)，完成情况见 [开发备忘录](docs/DEVELOPMENT_LOG.md)。

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ffmpeg-studio
```

启动后可拖入视频，或点击“选择视频”；在顶部切换转码、视频分割、提取音频，配置左侧参数并添加任务，然后在右侧启动队列、查看进度和日志。视频分割与音频提取均支持按原时长或指定每段秒数，音频默认输出 MP3。

项目开发环境会自动识别 `source/ffmpeg/bin` 中的 FFmpeg 与 FFprobe；其他环境可在“设置”中指定可执行文件路径。顶部横幅使用 `source/banner.jfif`。

运行测试：

```powershell
& .\env\Scripts\python.exe -m pytest --basetemp .\env\pytest-tmp
& .\env\Scripts\python.exe -m ruff check .
```
