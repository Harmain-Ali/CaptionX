# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: bundles Python, the backend, the built frontend, the DRT template and ffmpeg.
# Build from the repo root:  pyinstaller packaging/captionX.spec --noconfirm --distpath dist-win --workpath build-win
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "dist"
FFMPEG = ROOT / "packaging" / "ffmpeg"
ICON = ROOT / "assets" / "icon.ico"

if not (FRONTEND / "index.html").exists():
    raise SystemExit("frontend/dist is missing. Run `pnpm install && pnpm build` in frontend/ first.")

exe_ext = ".exe" if sys.platform == "win32" else ""
binaries = [(str(FFMPEG / f"{n}{exe_ext}"), ".") for n in ("ffmpeg", "ffprobe") if (FFMPEG / f"{n}{exe_ext}").exists()]
if sys.platform == "win32" and len(binaries) != 2:
    raise SystemExit("packaging/ffmpeg/ffmpeg.exe and ffprobe.exe are missing. Run packaging/get-ffmpeg.ps1 first.")

datas = [
    (str(FRONTEND), "frontend_dist"),
    (str(BACKEND / "app" / "templates"), "app/templates"),
]
hidden = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + collect_submodules("groq")
    + ["h11", "multipart", "python_multipart", "pystray", "PIL.Image", "PIL.ImageDraw"]
)
if sys.platform == "win32":
    hidden += ["pystray._win32"]

a = Analysis(
    [str(BACKEND / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "lupa", "matplotlib", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="captionX",
    console=False,            # no black console window: it lives in the tray
    icon=str(ICON) if ICON.exists() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="captionX", upx=False)
