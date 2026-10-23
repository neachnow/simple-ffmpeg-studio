"""Resolve bundled resources in development and frozen Windows builds."""

from __future__ import annotations

import sys
from pathlib import Path


def source_path(*parts: str) -> Path:
    """Return a path beneath the project's or bundle's source assets."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "source" / Path(*parts)
