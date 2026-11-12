"""Fusion `.setting` for ONE Text+ whose StyledText is keyframed: the text changes at every caption time.

No scripting needed. In Resolve (free too): select a Text+ clip, open the Fusion page, right-click the Text+ node,
Settings > Load Settings... and pick this file. (Pasting the same text with Ctrl+V into the node editor also works.)
The file is a Lua table, the format Fusion itself saves.
"""
from __future__ import annotations

import re
from fractions import Fraction

from .config import Settings
from .errors import AppError
from .fcpxml import CTRL, FPS_TABLE, frame_spans, parse_resolution
from .segmenter import Cue
from .srt import cue_text

TOOL = "Captions"
SPLINE = "CaptionsStyledText"


def lua_str(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\t", " ").replace("\n", "\\n")
    return f'"{s}"'


def _rgb(hex_color: str) -> list[float]:
    h = hex_color.lstrip("#")
    return [round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]


def keyframes(cues: list[Cue], offset_ms: int, fd: Fraction, casing: str, max_chars: int, script: str) -> dict[int, str]:
    """frame -> text. A blank key closes each caption; the next caption's key wins when they touch."""
    spans = frame_spans(cues, offset_ms, fd)
    keys: dict[int, str] = {}
    for c, sf, ef in spans:
        keys[ef] = ""
    for c, sf, ef in spans:
        keys[sf] = CTRL.sub("", cue_text(c, script, casing, max_chars))
    keys.setdefault(0, "")
    return dict(sorted(keys.items()))


def to_fusion_setting(cues: list[Cue], *, style: Settings, fps: str, resolution: str, offset_ms: int = 0,
                      casing: str = "natural", max_chars: int = 32, script: str = "roman") -> str:
    if fps not in FPS_TABLE:
        raise AppError("INVALID_REQUEST", f"Unsupported frame rate '{fps}'.", f"Use one of: {', '.join(FPS_TABLE)}.", 422)
    width, height = parse_resolution(resolution)
    num, den = FPS_TABLE[fps]
    keys = keyframes(cues, offset_ms, Fraction(num, den), casing, max_chars, script)
    if not any(keys.values()):
        raise AppError("NO_CAPTIONS", "There are no captions to export.", None, 409)
    r, g, b = _rgb(style.fcpxml_text_color)
    y = round(1 - style.fcpxml_position_y, 3)  # Fusion: 0 = bottom, 1 = top
    size = round(style.fcpxml_font_size / height, 4)

    t = "\t"
    kf = "".join(
        f'{t*4}[{f}] = {{ 0, Flags = {{ Linear = true, LockedY = true }}, Value = Text {{ Value = {lua_str(txt)} }} }},\n'
        for f, txt in keys.items()
    )
    face = style.fcpxml_font_face.strip()
    return (
        "{\n"
        f"{t}Tools = ordered() {{\n"
        f"{t*2}{TOOL} = TextPlus {{\n"
        f"{t*3}Inputs = {{\n"
        f"{t*4}Width = Input {{ Value = {width}, }},\n"
        f"{t*4}Height = Input {{ Value = {height}, }},\n"
        f"{t*4}UseFrameFormatSettings = Input {{ Value = 1, }},\n"
        f"{t*4}Center = Input {{ Value = {{ 0.5, {y} }}, }},\n"
        f"{t*4}Font = Input {{ Value = {lua_str(style.fcpxml_font)}, }},\n"
        + (f"{t*4}Style = Input {{ Value = {lua_str(face)}, }},\n" if face else "")
        + f"{t*4}Size = Input {{ Value = {size}, }},\n"
        f"{t*4}Red1 = Input {{ Value = {r}, }},\n"
        f"{t*4}Green1 = Input {{ Value = {g}, }},\n"
        f"{t*4}Blue1 = Input {{ Value = {b}, }},\n"
        f'{t*4}StyledText = Input {{ SourceOp = "{SPLINE}", Source = "Value", }},\n'
        f"{t*3}}},\n"
        f"{t*3}ViewInfo = OperatorInfo {{ Pos = {{ 0, 0 }} }},\n"
        f"{t*2}}},\n"
        f"{t*2}{SPLINE} = BezierSpline {{\n"
        f"{t*3}SplineColor = {{ Red = 237, Green = 142, Blue = 243 }},\n"
        f"{t*3}NameSet = true,\n"
        f"{t*3}KeyFrames = {{\n"
        f"{kf}"
        f"{t*3}}},\n"
        f"{t*2}}},\n"
        f"{t}}},\n"
        f'{t}ActiveTool = "{TOOL}"\n'
        "}\n"
    )
