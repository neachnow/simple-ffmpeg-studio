# FFmpeg Studio 开发约定

## 项目简介

FFmpeg Studio 是一个基于 Python 和 PySide6 的 Windows 本地桌面应用。它将 FFmpeg/FFprobe 的常用媒体处理能力以图形界面呈现，MVP 包含环境检测、转码、裁剪、音频提取、任务队列、进度和日志。

完整产品范围、里程碑与验收标准见 [`docs/PRD.md`](docs/PRD.md)。

## 开发环境

- 仅使用项目根目录的 `env` 虚拟环境；其解释器必须为 Python 3.12。
- 在 PowerShell 中执行 Python：`& .\env\Scripts\python.exe`。
- 所有新 Python 依赖都必须安装到 `env`，不得使用系统 Python 或全局 pip。
- 新增运行时依赖写入 `pyproject.toml` 的 `project.dependencies`；开发/测试依赖写入 `project.optional-dependencies.dev`。
- 首次安装或依赖变更后，使用：`& .\env\Scripts\python.exe -m pip install -e ".[dev]"`。

## 开发流程

1. 先阅读 PRD，并将当前改动限定在一个里程碑任务内。
2. 实现功能与相应测试；涉及 FFmpeg 执行的集成测试使用 `source` 目录中的媒体文件，绝不使用或修改工作区外文件。
3. 运行与本任务相关的测试；在可行时同时运行完整测试套件。
4. 测试通过后才能开始下一项任务。若因环境、依赖或外部工具无法测试，停止后续开发并明确记录阻碍。
5. 每个完成且测试通过的任务必须独立创建一个 Git commit，提交信息使用简洁的祈使句，例如 `feat: add FFmpeg executable discovery`。

## 安全与媒体处理规则

- 使用参数列表调用 `subprocess.Popen`，禁止拼接 shell 命令字符串执行 FFmpeg。
- 不得覆盖、移动或删除源媒体文件；默认输出写入源文件同级的 `FFmpeg Studio Output` 目录，并避免覆盖重名文件。
- 测试产生的输出放在可清理的临时目录，或在 `.gitignore` 排除的测试输出目录中。
- 支持含空格、中文和 Unicode 字符的文件路径。
- 不提交 `env`、构建产物、测试生成的媒体、日志或用户本机配置。
