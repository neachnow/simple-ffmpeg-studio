# 开发备忘录

本文件记录每个已完成开发任务的范围、验证结果及对应 Git commit。进行中的任务会标注阻碍，不能视为完成。

| 日期 | 任务 | 状态 | 验证结果 | Commit |
| --- | --- | --- | --- | --- |
| 2026-10-24 | 建立项目开发约定 | 已完成 | `git diff --cached --check -- AGENTS.md` 通过 | `cd84678` |
| 2026-10-24 | M0：项目骨架与开发约定 | 已完成 | Python 3.12 `env` 中执行 `pytest`：3 passed；执行 `ruff check .`：通过 | `feat: initialize application scaffold` |
| 2026-10-24 | M1：FFmpeg 核心能力 | 已完成 | 单元测试 `pytest`：11 passed；`ruff check .`：通过。使用 `source` 视频完成项目代码 `ffprobe` 探测（245.362 秒、2 条流）和 FFmpeg 1 秒 `-c copy` 临时输出验证（690,844 字节），临时输出已清理 | `629cf97` |
| 2026-10-24 | M2：主界面、转码、视频分割与音频提取 | 已完成 | `pytest`：19 passed（含 source 视频短片段 MP3 提取、视频分割、后台执行及 UI 转码）；`ruff check .`：通过；横幅及分割页截图已检查 | `feat: build media dashboard workflows` |
| 2026-10-24 | M3a：裁剪与音频高级参数 | 已完成 | `pytest`：21 passed（含 source 视频短片段裁剪、画面裁切与旋转）；`ruff check .`：通过；裁剪页滚动布局截图已检查 | `feat: add trim and audio controls` |
| 2026-10-24 | M3b：队列编辑、重试、历史及应用图标 | 已完成 | `pytest`：24 passed（含队列操作、Unicode 历史存取、图标加载及 source 视频 UI 转码）；`ruff check .`：通过 | `feat: manage queue history and app icon` |
| 2026-10-24 | M4：状态栏 Logo、圆角、Windows 试用包与使用说明 | 已完成 | `pytest`：24 passed；`ruff check .`：通过；源码及 PyInstaller 成品 `--smoke-test` 均通过，且成品在仅含 Windows System32 的 PATH 下启动检查通过；最终界面截图已检查。打包 exe 使用 `source/icon2.jpg`，FFmpeg 二进制不随包分发。 | `feat: package Windows trial build` |
| 2026-10-24 | M5a：时间轴任意切点的处理核心 | 已完成 | `pytest`：27 passed（含 `source` 视频的切点分割与音频提取实跑）；`ruff check .`：通过 | `feat: plan arbitrary timeline cuts` |

## 环境记录

- 目标解释器：`env\\Scripts\\python.exe`（Python 3.12.10）。
- 测试媒体：仅使用 `source` 目录中的文件。
- 当前测试命令：`& .\\env\\Scripts\\python.exe -m pytest --basetemp .\\env\\pytest-tmp`。
