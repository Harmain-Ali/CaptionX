"""FCPXML 1.9 export: one <title> per caption, frame-accurate, on lane 1 over a single gap.

DaVinci Resolve imports this via File > Import > Timeline. The title effect below is Final Cut's
"Basic Title"; Resolve maps it to one of its own title generators. TITLE_EFFECT is the single place
to change if a different title template (e.g. Resolve's Text+) needs to be referenced.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from .config import Settings
from .errors import AppError
from .segmenter import Cue
from .srt import _shifted, cue_text

FPS_TABLE = {
    "23.976": (1001, 24000), "24": (1, 24), "25": (1, 25), "29.97": (1001, 30000),
    "30": (1, 30), "50": (1, 50), "59.94": (1001, 60000), "60": (1, 60),
}
RESOLUTION_RE = re.compile(r"^(\d{3,4})x(\d{3,4})$")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

TITLE_EFFECT = {
    "name": "Basic Title",
    "uid": ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti",
}
POSITION_PARAM_KEY = "9999/999166631/999166667/1/100/101"  # Basic Title > Position


def parse_resolution(value: str) -> tuple[int, int]:
    m = RESOLUTION_RE.match((value or "").strip())
    if not m:
        raise AppError("INVALID_REQUEST", f"'{value}' isn't a valid resolution.", "Use the form 1080x1920.", 422)
    w, h = int(m.group(1)), int(m.group(2))
    if not (240 <= w <= 8192 and 240 <= h <= 8192):
        raise AppError("INVALID_REQUEST", "Resolution must be between 240 and 8192 pixels per side.", None, 422)
    return w, h


def _rt(frames: int, fd: Fraction) -> str:
    t = fd * frames
    return f"{t.numerator}s" if t.denominator == 1 else f"{t.numerator}/{t.denominator}s"


def _rgba(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return f"{r:.4f} {g:.4f} {b:.4f} 1"


def frame_spans(cues: list[Cue], offset_ms: int, fd: Fraction) -> list[tuple[Cue, int, int]]:
    """(cue, start_frame, end_frame): whole frames, at least 1 frame long, never overlapping."""
    out: list[tuple[Cue, int, int]] = []
    prev_end = 0
    for c, s, e in _shifted(cues, offset_ms):
        sf = max(round(Fraction(s).limit_denominator(100000) / fd), prev_end)
        ef = max(round(Fraction(e).limit_denominator(100000) / fd), sf + 1)
        out.append((c, sf, ef))
        prev_end = ef
    # a title must not run into the next one after rounding
    for i in range(len(out) - 1):
        c, sf, ef = out[i]
        nxt = out[i + 1][1]
        if ef > nxt:
            out[i] = (c, sf, max(sf + 1, nxt))
    return out


def to_fcpxml(cues: list[Cue], *, name: str, style: Settings, fps: str, resolution: str,
              offset_ms: int = 0, casing: str = "natural", max_chars: int = 32, script: str = "roman") -> str:
    if fps not in FPS_TABLE:
        raise AppError("INVALID_REQUEST", f"Unsupported frame rate '{fps}'.", f"Use one of: {', '.join(FPS_TABLE)}.", 422)
    width, height = parse_resolution(resolution)
    num, den = FPS_TABLE[fps]
    fd = Fraction(num, den)
    spans = frame_spans(cues, offset_ms, fd)
    if not spans:
        raise AppError("NO_CAPTIONS", "There are no captions to export.", None, 409)
    total = spans[-1][2]
    title_name = CTRL.sub("", name).strip() or "Roman Urdu Captions"

    root = ET.Element("fcpxml", version="1.9")
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r1", frameDuration=_rt(1, fd), width=str(width), height=str(height),
                  colorSpace="1-1-1 (Rec. 709)")
    ET.SubElement(res, "effect", id="r2", name=TITLE_EFFECT["name"], uid=TITLE_EFFECT["uid"])
    event = ET.SubElement(ET.SubElement(root, "library"), "event", name=title_name)
    project = ET.SubElement(event, "project", name=title_name)
    seq = ET.SubElement(project, "sequence", format="r1", duration=_rt(total, fd), tcStart="0s",
                        tcFormat="NDF", audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(seq, "spine")
    gap = ET.SubElement(spine, "gap", name="Gap", offset="0s", start="0s", duration=_rt(total, fd))

    y = round((0.5 - style.fcpxml_position_y) * height)  # FCP: 0,0 = centre, negative = below
    for n, (c, sf, ef) in enumerate(spans, start=1):
        text = CTRL.sub("", cue_text(c, script, casing, max_chars))
        title = ET.SubElement(gap, "title", ref="r2", lane="1", offset=_rt(sf, fd), name=f"Caption {n:03d}",
                              start="3600s", duration=_rt(ef - sf, fd))
        ET.SubElement(title, "param", name="Position", key=POSITION_PARAM_KEY, value=f"0 {y}")
        sid = f"ts{n}"
        ET.SubElement(ET.SubElement(title, "text"), "text-style", ref=sid).text = text
        defn = ET.SubElement(title, "text-style-def", id=sid)
        attrs = {"font": style.fcpxml_font, "fontSize": str(style.fcpxml_font_size),
                 "fontColor": _rgba(style.fcpxml_text_color), "alignment": "center"}
        if style.fcpxml_font_face.strip():
            attrs["fontFace"] = style.fcpxml_font_face.strip()
        if style.fcpxml_font_face.strip().lower() == "bold":
            attrs["bold"] = "1"
        if style.fcpxml_outline:
            attrs["strokeColor"] = _rgba(style.fcpxml_outline_color)
            attrs["strokeWidth"] = "-3"
        ET.SubElement(defn, "text-style", **attrs)

    ET.indent(root, space="    ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(root, encoding="unicode") + "\n"


def project_name(filename: str) -> str:
    return Path(filename).stem or "Roman Urdu Captions"
