"""captionX desktop launcher (the entry point of the packaged Windows app).

Starts the server on 127.0.0.1, opens captionX in its own app window, and quits by itself when that window is closed
(a tray icon gives Open / Quit while it runs).
Set CAPTIONX_HEADLESS=1 to run the server only (used by the build's smoke test).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

PREFERRED_PORT = 8765


def _prepare() -> None:
    """Environment must be ready BEFORE the app modules are imported."""
    from app import paths

    data = paths.default_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("CAPTIONS_DATA_DIR", str(data))
    # A windowed exe has no console: send output to a log file so errors are never lost (and uvicorn never trips on None).
    log = open(data / "captionx.log", "a", buffering=1, encoding="utf-8", errors="replace")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    # Use the ffmpeg that ships with the app before anything on the system PATH.
    names = ("ffmpeg.exe", "ffprobe.exe") if os.name == "nt" else ("ffmpeg", "ffprobe")
    for d in paths.ffmpeg_dirs():
        if all((d / n).exists() for n in names):
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            break


def _is_ours(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            d = json.loads(r.read().decode("utf-8"))
        return bool(d.get("ok")) and "version" in d
    except Exception:
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _pick_port() -> int:
    if _port_free(PREFERRED_PORT):
        return PREFERRED_PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _message(title: str, text: str, blocking: bool = True) -> None:
    """Native message box on Windows; stderr elsewhere."""
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40 if blocking else 0x10)  # type: ignore[attr-defined]
    else:
        print(f"{title}: {text}", file=sys.stderr)


def _app_browser() -> str | None:
    """Edge (always on Windows 10/11) or Chrome, to show captionX as its own window with its own taskbar button."""
    pf, pf86, local = (os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"))
    for base, rel in (
        (pf86, r"Microsoft\Edge\Application\msedge.exe"), (pf, r"Microsoft\Edge\Application\msedge.exe"),
        (pf, r"Google\Chrome\Application\chrome.exe"), (pf86, r"Google\Chrome\Application\chrome.exe"),
        (local, r"Google\Chrome\Application\chrome.exe"),
    ):
        if base and (Path(base) / rel).exists():
            return str(Path(base) / rel)
    return None


def _brand_window(timeout: float = 25.0) -> None:
    """Windows: give the captionX window our own taskbar icon and identity instead of Edge/Chrome's."""
    import ctypes
    from ctypes import wintypes

    from app import paths

    ico = paths.bundle_dir() / "assets" / "icon.ico"
    if not ico.exists():
        return
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
    ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]

    def load(size: int):
        return user32.LoadImageW(None, str(ico), 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE

    big, small = load(256), load(16)

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

    def guid(s: str) -> GUID:
        import uuid
        u = uuid.UUID(s)
        g = GUID()
        g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
        for i, byte in enumerate(u.bytes[8:]):
            g.d[i] = byte
        return g

    class KEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                    ("r3", ctypes.c_ushort), ("p", ctypes.c_void_p), ("pad", ctypes.c_void_p)]

    def set_identity(hwnd) -> None:
        store = ctypes.c_void_p()
        iid = guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")  # IID_IPropertyStore
        if shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store)) != 0 or not store:
            return
        vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(KEY), ctypes.POINTER(PROPVARIANT))(vtbl[6])
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtbl[7])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        fmt = "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"
        exe = sys.executable
        for pid, value in ((5, "Harmain.captionX"), (2, f'"{exe}"'), (4, "captionX"), (3, f"{ico},0")):
            buf = ctypes.create_unicode_buffer(value)
            pv = PROPVARIANT(vt=31, p=ctypes.cast(buf, ctypes.c_void_p).value)  # VT_LPWSTR
            set_value(store, ctypes.byref(KEY(guid(fmt), pid)), ctypes.byref(pv))
        commit(store)
        release(store)

    done: set[int] = set()
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _lparam):
        if hwnd in done or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        if cls.value == "Chrome_WidgetWin_1" and title.value.startswith("captionX"):
            done.add(hwnd)
            try:
                set_identity(hwnd)
            except Exception:
                pass
            user32.SendMessageW(hwnd, 0x80, 1, big)    # WM_SETICON, ICON_BIG
            user32.SendMessageW(hwnd, 0x80, 0, small)  # ICON_SMALL
        return True

    callback = enum_proc(visit)
    deadline = time.time() + timeout
    while time.time() < deadline:
        user32.EnumWindows(callback, 0)
        if done:
            return
        time.sleep(0.4)


def _open_window(url: str, data_dir: Path) -> None:
    """Own app window (no tabs or address bar) with a separate browser profile; falls back to the default browser."""
    exe = _app_browser() if os.name == "nt" else None
    if exe:
        try:
            subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={data_dir / 'window'}", "--no-first-run",
                              "--no-default-browser-check", "--window-size=1380,900", "--disable-features=Translate"])
            threading.Thread(target=lambda: _safe(_brand_window), name="captionx-icon", daemon=True).start()
            return
        except OSError:
            pass
    webbrowser.open(url)


def _safe(fn) -> None:
    try:
        fn()
    except Exception:
        pass


def _tray_image():
    from PIL import Image, ImageDraw
    size = 128
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=38, fill=(255, 76, 0, 255))
    w = 14
    d.line((40, 40, 88, 88), fill=(10, 10, 10, 255), width=w)
    d.line((88, 40, 40, 88), fill=(10, 10, 10, 255), width=w)
    for x, y in ((40, 40), (88, 88), (88, 40), (40, 88)):
        d.ellipse((x - w // 2, y - w // 2, x + w // 2, y + w // 2), fill=(10, 10, 10, 255))
    return img


def main() -> int:
    _prepare()
    from app import paths

    if _is_ours(PREFERRED_PORT) and not os.environ.get("CAPTIONX_HEADLESS"):
        _open_window(f"http://127.0.0.1:{PREFERRED_PORT}", paths.default_data_dir())  # already running: bring it up
        return 0

    import uvicorn
    from app.main import app

    port = _pick_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None,
                                           loop="asyncio", http="h11", ws="none", lifespan="on"))
    thread = threading.Thread(target=server.run, name="captionx-server", daemon=True)
    thread.start()
    t0 = time.time()
    while not server.started and thread.is_alive() and time.time() - t0 < 40:
        time.sleep(0.1)
    if not server.started:
        _message("captionX could not start", f"The local server did not start.\nDetails are in:\n{paths.default_data_dir() / 'captionx.log'}", False)
        return 1

    tray: dict = {"icon": None}

    def quit_app(icon=None, item=None):
        server.should_exit = True
        ic = icon or tray["icon"]
        if ic is not None:
            try:
                ic.stop()
            except Exception:
                pass

    def watchdog():
        """Quit by itself once the captionX window is closed (never during a running job)."""
        from app.main import jobs
        from app.presence import presence
        while thread.is_alive():
            time.sleep(1)
            busy = any(j.get("status") in ("queued", "running") for j in jobs.list())
            if presence.should_quit(busy):
                print("window closed, quitting", flush=True)
                quit_app()
                time.sleep(1.5)
                os._exit(0)  # also ends the fallback dialog if the tray never started

    if os.environ.get("CAPTIONX_HEADLESS"):
        print(f"captionX headless on {url}", flush=True)
        if os.environ.get("CAPTIONX_AUTOQUIT"):
            threading.Thread(target=watchdog, name="captionx-watchdog", daemon=True).start()
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            server.should_exit = True
        return 0

    _open_window(url, paths.default_data_dir())
    threading.Thread(target=watchdog, name="captionx-watchdog", daemon=True).start()

    try:
        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("Open captionX", lambda icon, item: _open_window(url, paths.default_data_dir()), default=True),
            pystray.MenuItem("Open data folder", lambda icon, item: os.startfile(str(paths.default_data_dir())) if os.name == "nt" else None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit captionX", quit_app),
        )
        tray["icon"] = pystray.Icon("captionX", _tray_image(), "captionX", menu)
        tray["icon"].run()  # blocks until Quit
    except Exception as e:  # no tray available: a dialog keeps the app alive; OK quits it
        print(f"tray unavailable ({e!r})", file=sys.stderr)
        _message("captionX is running", f"captionX is open in your browser at\n{url}\n\nClick OK to quit captionX.")
    server.should_exit = True
    thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
