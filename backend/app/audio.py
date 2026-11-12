"""ffmpeg/ffprobe helpers: probe, convert for Whisper, chunk, make a browser preview."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .errors import AppError

API_MAX_BYTES = 24 * 1024 * 1024  # Groq free tier limit is 25 MB per file


def ffmpeg_path() -> Optional[str]:
    return shutil.which("ffmpeg")


def ffprobe_path() -> Optional[str]:
    return shutil.which("ffprobe")


def tools_status() -> dict:
    return {"ffmpeg": ffmpeg_path() is not None, "ffprobe": ffprobe_path() is not None}


def require_tools() -> None:
    if not (ffmpeg_path() and ffprobe_path()):
        raise AppError(
            "FFMPEG_MISSING", "ffmpeg / ffprobe was not found on this computer.",
            "Install ffmpeg (Windows: winget install Gyan.FFmpeg · macOS: brew install ffmpeg · "
            "Linux: sudo apt install ffmpeg), then restart the backend.", 500, "prepare")


# On Windows a packaged (windowed) app would flash a console window for every ffmpeg call without this.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired as e:
        raise AppError("MEDIA_TIMEOUT", "Processing the media file took too long.",
                       "Try a shorter file.", 500, "prepare") from e
    except FileNotFoundError as e:
        raise AppError("FFMPEG_MISSING", "ffmpeg was not found.", None, 500, "prepare") from e


@dataclass
class MediaInfo:
    duration: float
    has_audio: bool
    has_video: bool


def probe(path: Path) -> MediaInfo:
    p = _run([ffprobe_path() or "ffprobe", "-v", "error", "-show_format", "-show_streams",
              "-of", "json", str(path)], timeout=60)
    if p.returncode != 0:
        raise AppError("UNSUPPORTED_MEDIA", "This file could not be read as audio or video.",
                       "Export it again as MP3, WAV, M4A or MP4 and retry.", 415, "prepare")
    try:
        info = json.loads(p.stdout or "{}")
    except json.JSONDecodeError as e:
        raise AppError("UNSUPPORTED_MEDIA", "Could not read media information.", None, 415, "prepare") from e
    streams = info.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1
                    for s in streams)
    dur = 0.0
    try:
        dur = float(info.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        pass
    if dur <= 0:
        for s in streams:
            try:
                dur = max(dur, float(s.get("duration") or 0))
            except (TypeError, ValueError):
                pass
    return MediaInfo(duration=dur, has_audio=has_audio, has_video=has_video)


def max_volume_db(path: Path) -> Optional[float]:
    """Loudest sample in dB (0 = full scale). None if it could not be measured."""
    p = _run([ffmpeg_path() or "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path),
              "-vn", "-af", "volumedetect", "-f", "null", "-"], timeout=600)
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf)\s*dB", p.stderr or "")
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


@dataclass
class Chunk:
    path: Path
    offset: float
    duration: float


def _encode_args(fmt: str) -> list[str]:
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", "48k"]
    return ["-c:a", "flac"]


def prepare_stt_audio(
    src: Path, out_dir: Path, fmt: str, chunk_seconds: int,
    cancel: Optional[Callable[[], None]] = None,
) -> list[Chunk]:
    """Convert to 16 kHz mono (what Whisper uses internally) and split into API-sized chunks."""
    ff = ffmpeg_path() or "ffmpeg"
    ext = "mp3" if fmt == "mp3" else "flac"
    full = out_dir / f"stt_full.{ext}"
    p = _run([ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
              "-vn", "-ac", "1", "-ar", "16000", *_encode_args(fmt), str(full)])
    if p.returncode != 0 or not full.exists() or full.stat().st_size == 0:
        raise AppError("MEDIA_DECODE_FAILED", "ffmpeg could not decode the audio.",
                       (p.stderr or "").strip().splitlines()[-1] if p.stderr else None, 415, "prepare")

    total = probe(full).duration
    seg_len = chunk_seconds
    while True:
        if cancel:
            cancel()
        needs_split = total > seg_len or full.stat().st_size > API_MAX_BYTES
        if not needs_split:
            return [Chunk(full, 0.0, total)]
        for old in out_dir.glob(f"chunk_*.{ext}"):
            old.unlink()
        listing = out_dir / "chunks.csv"
        listing.unlink(missing_ok=True)
        # Re-encode instead of `-c copy`: copied FLAC chunks keep the WHOLE file's length in their header.
        # Chunk times come from ffmpeg's own segment list: the segment muxer cannot rewrite the
        # header length afterwards, so ffprobe on the chunk files returns nothing useful.
        p = _run([ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(full),
                  "-f", "segment", "-segment_time", str(seg_len),
                  "-segment_list", str(listing), "-segment_list_type", "csv",
                  *_encode_args(fmt), str(out_dir / f"chunk_%03d.{ext}")])
        files = sorted(out_dir.glob(f"chunk_*.{ext}"))
        if p.returncode != 0 or not files:
            raise AppError("MEDIA_DECODE_FAILED", "Could not split the audio into chunks.", None, 500, "prepare")
        if any(f.stat().st_size > API_MAX_BYTES for f in files) and seg_len > 60:
            seg_len = max(60, seg_len // 2)  # still too big: halve and retry
            continue
        return _chunks_from_listing(files, listing, total)


def _chunks_from_listing(files: list[Path], listing: Path, total: float) -> list[Chunk]:
    times: dict[str, tuple[float, float]] = {}
    try:
        for line in listing.read_text(encoding="utf-8").splitlines():
            name, start, end = line.rsplit(",", 2)
            times[Path(name.strip().strip('"')).name] = (float(start), float(end))
    except (OSError, ValueError):
        times = {}
    if len(times) != len(files) or any(f.name not in times for f in files):
        # Fallback: decode each chunk and measure it. Slower but always correct.
        chunks, offset = [], 0.0
        for f in files:
            d = decoded_duration(f)
            chunks.append(Chunk(f, offset, d))
            offset += d
        return chunks
    return [Chunk(f, times[f.name][0], max(times[f.name][1] - times[f.name][0], 0.0)) for f in files]


def decoded_duration(path: Path) -> float:
    """Duration by actually decoding (headers can be missing in streamed files)."""
    p = _run([ffmpeg_path() or "ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-f", "null", "-"], timeout=600)
    times = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", p.stderr or "")
    if not times:
        return 0.0
    h, m, s = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def make_preview(src: Path, dest: Path) -> None:
    """Browser-friendly mono MP3 for the caption preview player."""
    p = _run([ffmpeg_path() or "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
              "-i", str(src), "-vn", "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "96k",
              str(dest)])
    if p.returncode != 0 or not dest.exists():
        raise AppError("MEDIA_DECODE_FAILED", "Could not create the preview audio.", None, 500, "prepare")
