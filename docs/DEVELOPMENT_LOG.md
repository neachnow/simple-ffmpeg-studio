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
| 2026-10-24 | M5b：1.0.1 可视化时间轴、紧凑布局与发布 | 已完成 | `pytest`：30 passed（含时间轴切点拖动/删除、裁剪双向同步、`source` 视频缩略图提取和任务命令）；`ruff check .`、源码启动检查通过。时间轴画面条 120px、横幅 133px；850px 初始窗口下裁剪与音频页首排四参数、无水平/垂直滚动，可最大化。PyInstaller 成品构建及仅含 Windows System32 的 PATH 下启动检查通过；FFmpeg/FFprobe 仍需用户配置。 | `feat: release visual timeline in 1.0.1` |
| 2026-10-24 | M6a：裁剪及音频固定四列参数网格 | 已完成 | `pytest`：30 passed；`ruff check .`：通过；850px 窗口截图已检查。两页第二排第四列均留空，第二排三个参数与第一排同宽，没有纵向或横向溢出。 | `feat: align processing parameters in four columns` |
| 2026-10-24 | M6b：可替换窗口背景或顶部横幅 | 已完成 | `pytest`：32 passed（含图片立即应用、输入框与左下内容卡片透出背景、持久化重启、清除和无效图片回退）；`ruff check .`：通过；截图确认左下滚动卡片四周圆角及透明背景。横幅与时间轴画面仍不透明；深色小字配浅色柔光以增强复杂背景上的可读性。 | `feat: customize workspace background` |
| 2026-10-24 | M6c：1.0.3 发布及 Windows 打包 | 已完成 | 按后续界面要求将原定 1.0.2 调整为 1.0.3；在 Python 3.12 `env` 重装项目后 `pytest`：32 passed（含 `source` 媒体集成测试）；`ruff check .`、源码 `--smoke-test` 通过。PyInstaller 构建通过，成品在仅含 Windows System32 的 PATH 下 `--smoke-test` 退出码 0；FFmpeg/FFprobe 不随包分发。 | `feat: release FFmpeg Studio 1.0.3` |
| 2026-10-24 | M6d：README 内嵌 UI6 界面预览 | 已完成 | 检查 `docs/UI6.png` 可读取，并验证 README 中的相对图片路径指向该文件；完整测试和静态检查通过。 | `docs: show UI6 preview in README` |

## 环境记录

- 目标解释器：`env\\Scripts\\python.exe`（Python 3.12.10）。
- 测试媒体：仅使用 `source` 目录中的文件。
- 当前测试命令：`& .\\env\\Scripts\\python.exe -m pytest --basetemp .\\env\\pytest-tmp`。
