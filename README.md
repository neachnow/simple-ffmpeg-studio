# FFmpeg Studio

FFmpeg Studio 是一款 Windows 本地媒体处理工具，使用 Python 与 PySide6 将常用 FFmpeg 命令变成图形界面。选择视频、设置参数、加入队列后，即可在界面中查看处理进度、实际命令和执行日志。媒体文件在本机处理，不上传到云端。

> **使用前必须准备 FFmpeg 和 FFprobe。** FFmpeg Studio 是图形界面，不是编码器；没有可用的 `ffmpeg.exe` 与 `ffprobe.exe` 就无法分析或处理媒体。Windows 试用包**不内置**这两个程序。首次打开后，请在“设置 / Settings”页分别指定它们的完整路径，再点击“保存并检测”。`ffplay.exe` 不是必需的。

## 主要功能

- **转码 / Transcode：** 将视频转为 MP4（H.264/AAC），选择高质量、平衡或小体积预设。
- **视频分割 / Split Video：** 保持原时长输出，或按每段秒数生成多个视频。
- **裁剪 / Trim：** 设置起止时间，并可旋转、翻转或裁切画面。
- **提取音频 / Extract Audio：** 导出 MP3、AAC、WAV 或 FLAC；可选择完整时长或分段，并调整码率、采样率、声道和增益。
- **任务队列：** 添加多个任务，查看进度、命令预览和日志；等待中的任务可编辑输出路径、排序或移除，失败任务可重试。最近任务历史保存在本机，可在设置页清除。

## 开始使用

1. 准备可运行的 Windows 版 FFmpeg，找到同一套工具中的 `ffmpeg.exe` 和 `ffprobe.exe`。本项目开发目录提供的路径是 `source/ffmpeg/bin/`；分发的试用包不包含该目录。
2. 启动 FFmpeg Studio，进入“设置 / Settings”，分别选择两个 `.exe` 文件并保存。概览页应显示 FFmpeg 版本和“已就绪”。
3. 拖入媒体文件，或点击“选择视频”。左侧会显示时长、视频分辨率和音轨信息。
4. 切换顶部功能页，在左侧设置参数并点击“添加任务”；到右侧点击“开始队列”。
5. 默认输出位于源文件旁的 `FFmpeg Studio Output` 文件夹。同名文件会自动编号，不覆盖源文件或已有输出。

## Windows 试用包

构建结果在 `env/dist/FFmpeg Studio/`，运行其中的 `FFmpeg Studio.exe`。复制或分发时须保留**整个** `FFmpeg Studio` 目录，不能只复制 exe。横幅使用 `source/banner.jfif`，右下状态栏使用 `source/logo.jfif`，窗口图标使用 `source/icon.jfif`，exe 使用 `source/icon2.jpg` 转换的图标。

本试用包未随附 FFmpeg/FFprobe，也不自动下载或安装。若概览页显示“未找到”，先检查设置中的两个路径是否指向实际存在的 `.exe`，并确认它们可以在本机运行。若横幅或图标缺失，请确认试用包目录完整。

## 从源码运行与构建

开发环境限定为项目根目录的 Python 3.12 `env` 虚拟环境，所有依赖仅安装到该环境：

```powershell
py -3.12 -m venv env
& .\env\Scripts\python.exe -m pip install -e ".[dev]"
& .\env\Scripts\ffmpeg-studio.exe
```

构建 Windows 试用包：

```powershell
& .\env\Scripts\python.exe .\tools\build.py
```

构建脚本会把界面资源放入应用目录，并在构建后执行一次启动检查。运行测试和静态检查：

```powershell
& .\env\Scripts\python.exe -m pytest --basetemp .\env\pytest-tmp
& .\env\Scripts\python.exe -m ruff check .
```

产品范围与后续计划见 [PRD](docs/PRD.md)；任务完成与测试记录见 [开发备忘录](docs/DEVELOPMENT_LOG.md)。
