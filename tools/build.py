"""Build the Windows trial application with the active project interpreter."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from ctypes import windll
from pathlib import Path

from PySide6.QtGui import QImage


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    expected = root / "env" / "Scripts" / "python.exe"
    if Path(sys.executable).resolve() != expected.resolve():
        raise SystemExit("请使用项目 env\\Scripts\\python.exe 执行打包脚本")
    build_dir = root / "env" / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    icon = build_dir / "icon.ico"
    image = QImage(str(root / "source" / "icon2.jpg"))
    if image.isNull() or not image.save(str(icon), "ICO"):
        raise SystemExit("无法从 source/icon2.jpg 创建 Windows 打包图标")
    # Loading Qt in this builder changes the inherited Windows DLL search path.
    # Restore it so the frozen app uses its own Qt libraries during the smoke test.
    windll.kernel32.SetDllDirectoryW(None)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--console" if "--debug-console" in sys.argv else "--windowed",
        "--onedir", "--name", "FFmpeg Studio", "--icon", str(icon),
        "--paths", str(root / "src"),
        "--add-data", f"{root / 'source' / 'banner.jfif'};source",
        "--add-data", f"{root / 'source' / 'logo.jfif'};source",
        "--add-data", f"{root / 'source' / 'icon.jfif'};source",
        "--distpath", str(root / "env" / "dist"),
        "--workpath", str(build_dir / "pyinstaller"),
        "--specpath", str(build_dir),
        str(root / "src" / "ffmpeg_studio" / "app.py"),
    ]
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode:
        return result.returncode
    distribution = root / "env" / "dist" / "FFmpeg Studio"
    # A foreign ICU DLL on the build machine's PATH can be collected by
    # PyInstaller. Qt 6 expects Windows' native, unversioned ICU exports.
    foreign_icu = distribution / "_internal" / "icuuc.dll"
    if foreign_icu.is_file():
        foreign_icu.unlink()
    executable = distribution / "FFmpeg Studio.exe"
    smoke_env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    for attempt in range(3):
        smoke = subprocess.run(
            [str(executable), "--smoke-test"], cwd=distribution, env=smoke_env,
            check=False, timeout=30,
        )
        if smoke.returncode == 0:
            return 0
        if attempt < 2:
            time.sleep(2)
    return smoke.returncode


if __name__ == "__main__":
    raise SystemExit(main())
