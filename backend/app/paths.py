"""Where things live, for both `python run.py` (development) and the packaged Windows app."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Folder holding the packaged files (frontend, templates, ffmpeg). PyInstaller sets sys._MEIPASS."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def frontend_dist() -> Path:
    if is_frozen():
        return bundle_dir() / "frontend_dist"
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def default_data_dir(frozen: bool | None = None, platform: str | None = None, env: dict | None = None) -> Path:
    """Settings, history and audio. Installed apps can't write next to themselves, so they use a per-user folder."""
    frozen = is_frozen() if frozen is None else frozen
    platform = platform or sys.platform
    env = os.environ if env is None else env
    if not frozen:
        return Path(__file__).resolve().parent.parent / "data"
    if platform.startswith("win"):
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "captionX"
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "captionX"
    return Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "captionX"


def ffmpeg_dirs() -> list[Path]:
    """Folders that may hold a bundled ffmpeg/ffprobe, checked before the system PATH."""
    out = [bundle_dir()]
    if is_frozen():
        out.append(Path(sys.executable).resolve().parent)
    return out
