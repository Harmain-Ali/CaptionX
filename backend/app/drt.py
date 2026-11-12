"""DaVinci Resolve timeline (.drt) with ONE Text+ clip per caption.

A .drt is a zip of XML files. It was reverse-engineered from a timeline exported by Resolve 20.2 that held three
Text+ clips (app/templates/textplus_template.drt). Every Text+ clip stores a small Fusion composition in a blob:
    BE32 size + zlib( Qt-style key/value dump ), whose "_data" value is the comp text + NUL + LE32 + zlib(inner comp)
The inner comp holds the Text+ settings and the caption text. This module rewrites those pieces and clones the clip
element once per caption. NOT verified inside Resolve (no Resolve here); see README.
"""
from __future__ import annotations

import io
import re
import struct
import uuid
import zipfile
import zlib
from fractions import Fraction
from pathlib import Path

from .config import Settings
from .errors import AppError
from .fcpxml import CTRL, FPS_TABLE, frame_spans, parse_resolution
from .segmenter import Cue
from .srt import cue_text

TEMPLATE = Path(__file__).resolve().parent / "templates" / "textplus_template.drt"
SEQ_PATH = "SeqContainer/f9e6d9b2-3cf7-45ba-8774-e7db39ebf250.xml"
MP_PATH = "MediaPool/Master/MpFolder.xml"
PROJECT_PATH = "project.xml"
TPL_W, TPL_H, TPL_FPS = 1280, 720, 24
NOMINAL = {"23.976": 24, "24": 24, "25": 25, "29.97": 30, "30": 30, "50": 50, "59.94": 60, "60": 60}
BLOB = r'<(%s)>([0-9a-f]+)</\1>'


def lua_str(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\t", " ").replace("\n", "\\n")
    return f'"{s}"'


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4))  # type: ignore[return-value]


# ------------------------------------------------------------------ Fusion composition blob
def inner_comp(text: str, frames: int, width: int, height: int, style: Settings) -> str:
    r, g, b = _rgb(style.fcpxml_text_color)
    size = round(style.fcpxml_font_size / height, 4)
    y = round(1 - style.fcpxml_position_y, 3)
    face = style.fcpxml_font_face.strip()
    return (
        "{ Template = TextPlus { CtrlWZoom = false, Inputs = { "
        f"GlobalOut = Input {{ Value = {frames - 1}, }}, "
        f"Width = Input {{ Value = {width}, }}, Height = Input {{ Value = {height}, }}, "
        "UseFrameFormatSettings = Input { Value = 1, }, "
        f"StyledText = Input {{ Value = {lua_str(text)}, }}, "
        f"Font = Input {{ Value = {lua_str(style.fcpxml_font)}, }}, "
        + (f"Style = Input {{ Value = {lua_str(face)}, }}, " if face else "")
        + f"Size = Input {{ Value = {size}, }}, "
        f"Center = Input {{ Value = {{ 0.5, {y} }}, }}, "
        f"Red1 = Input {{ Value = {r}, }}, Green1 = Input {{ Value = {g}, }}, Blue1 = Input {{ Value = {b}, }}, "
        "VerticalJustificationNew = Input { Value = 3, }, HorizontalJustificationNew = Input { Value = 3, } }, "
        "ViewInfo = OperatorInfo { Pos = { 220, 49.5 } }, }, "
        "MediaOut1 = MediaOut { Inputs = { Index = Input { Value = \"0\", }, "
        "Input = Input { SourceOp = \"Template\", Source = \"Output\", } }, "
        "ViewInfo = OperatorInfo { Pos = { 440, 49.5 } }, } } "
    )


def _split_composition(raw: bytes) -> tuple[bytes, bytes, str]:
    """-> (prefix before the byte-array length, outer comp text, ignored). Validates the framing."""
    d = zlib.decompress(raw[4:])
    if struct.unpack(">I", raw[:4])[0] != len(d):
        raise ValueError("unexpected composition header")
    j = d.index(b"Composition {")
    arr_len = struct.unpack(">I", d[j - 4:j])[0]
    if j + arr_len != len(d):
        raise ValueError("unexpected composition framing")
    arr = d[j:]
    z = arr.index(b"\x00") + 1  # NUL right after the comp text
    return d[:j - 4], arr[:z - 1], arr[z + 4:].hex()


def build_composition(template_hex: str, *, text: str, frames: int, width: int, height: int,
                      fps_value: float, style: Settings) -> str:
    raw = bytes.fromhex(template_hex)
    d = zlib.decompress(raw[4:])
    j = d.index(b"Composition {")
    prefix = d[:j - 4]
    outer = d[j:].split(b"\x00", 1)[0].decode("utf-8")
    end = frames - 1
    outer = re.sub(r"RenderRange = \{ 0, \d+ \}", f"RenderRange = {{ 0, {end} }}", outer)
    outer = re.sub(r"GlobalRange = \{ 0, \d+ \}", f"GlobalRange = {{ 0, {end} }}", outer)
    outer = re.sub(r"GlobalEnd = \d+", f"GlobalEnd = {end}", outer)
    outer = re.sub(r"Width = \d+, Height = \d+, Rate = [\d.]+", f"Width = {width}, Height = {height}, Rate = {fps_value:g}", outer)
    outer = re.sub(r"GuideRatio = [\d.]+", f"GuideRatio = {width / height:.14g}", outer)
    outer = re.sub(r'Paths = \{ Map = \{.*?\}, \},', "Paths = { },", outer)  # drop the sample's local cache path
    inner = inner_comp(text, frames, width, height, style).encode("utf-8")
    arr = outer.encode("utf-8") + b"\x00" + struct.pack("<I", len(inner)) + zlib.compress(inner)
    body = prefix + struct.pack(">I", len(arr)) + arr
    return (struct.pack(">I", len(body)) + zlib.compress(body)).hex()


def read_text(comp_hex: str) -> str:
    """Caption text stored in a composition blob (used by tests and for self-checks)."""
    d = zlib.decompress(bytes.fromhex(comp_hex)[4:])
    arr = d[d.index(b"Composition {"):]
    inner = zlib.decompress(arr[arr.index(b"\x00") + 5:]).decode("utf-8")
    m = re.search(r'StyledText = Input \{ Value = ("(?:[^"\\]|\\.)*")', inner)
    return m.group(1)[1:-1].replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\") if m else ""


# ------------------------------------------------------------------ timeline settings (best effort)
def _patch_setup_blob(hexs: str, w: int, h: int, fps: int) -> str:
    raw = bytearray(bytes.fromhex(hexs))
    key = "SequenceSetup".encode("utf-16-be")
    k = bytes(raw).index(key) + len(key)
    t, _nul, ln = struct.unpack(">IBI", raw[k:k + 9])
    a = k + 9
    if t != 12 or ln != 359 or struct.unpack(">qq", raw[a + 40:a + 56]) != (TPL_W, TPL_H) \
            or struct.unpack(">I", raw[a + 80:a + 84])[0] != TPL_FPS:
        raise ValueError("timeline setup blob differs from the template")
    raw[a + 40:a + 56] = struct.pack(">qq", w, h)
    raw[a + 232:a + 236] = struct.pack(">I", w)
    raw[a + 240:a + 244] = struct.pack(">I", h)
    raw[a + 80:a + 84] = struct.pack(">I", fps)
    return bytes(raw).hex()


def _patch_mp(mp: str, w: int, h: int, fps_value: float, nominal: int, total_frames: int) -> str:
    def tag(name: str, old: str, new: str, s: str) -> str:
        assert f"<{name}>{old}</{name}>" in s, name
        return s.replace(f"<{name}>{old}</{name}>", f"<{name}>{new}</{name}>")
    fr_old = struct.pack("<dd", float(TPL_FPS), 0.0).hex()
    mp = tag("FrameRate", fr_old, struct.pack("<dd", fps_value, 0.0).hex(), mp)
    mp = tag("Resolution", struct.pack(">qq", TPL_W, TPL_H).hex(), struct.pack(">qq", w, h).hex(), mp)
    me_old = struct.pack("<dd", 3600.0, 165 / 24).hex()
    mp = tag("MediaExtents", me_old, struct.pack("<dd", 3600.0, total_frames / fps_value).hex(), mp)
    for fb in re.finditer(r"<FieldsBlob>([0-9a-f]+)</FieldsBlob>", mp):
        if "SequenceSetup".encode("utf-16-be").hex() in fb.group(1):
            mp = mp.replace(fb.group(1), _patch_setup_blob(fb.group(1), w, h, nominal), 1)
            break
    else:
        raise ValueError("no SequenceSetup blob")
    return mp


# ------------------------------------------------------------------ main entry
def to_drt(cues: list[Cue], *, style: Settings, fps: str, resolution: str, offset_ms: int = 0,
           casing: str = "natural", max_chars: int = 32, script: str = "roman") -> bytes:
    if fps not in FPS_TABLE:
        raise AppError("INVALID_REQUEST", f"Unsupported frame rate '{fps}'.", f"Use one of: {', '.join(FPS_TABLE)}.", 422)
    width, height = parse_resolution(resolution)
    num, den = FPS_TABLE[fps]
    fd = Fraction(num, den)
    spans = frame_spans(cues, offset_ms, fd)
    if not spans:
        raise AppError("NO_CAPTIONS", "There are no captions to export.", None, 409)
    nominal = NOMINAL[fps]
    fps_value = float(Fraction(den, num))
    base = 3600 * nominal  # clips start at 01:00:00:00, Resolve's default timeline start

    try:
        with zipfile.ZipFile(TEMPLATE) as z:
            files = {n: z.read(n) for n in z.namelist()}
        seq = files[SEQ_PATH].decode("utf-8")
        els = list(re.finditer(r"<Element>\s*<Sm2TiVideoClip.*?</Sm2TiVideoClip>\s*</Element>", seq, re.S))
        if not els:
            raise ValueError("no clip in template")
        a, b = els[0].start(), els[0].end()
        clip_tpl = seq[a:b]
        last_end = els[-1].end()
        tpl_hex = re.search(BLOB % "CompositionBA", clip_tpl).group(2)

        out: list[str] = []
        for c, sf, ef in spans:
            frames = ef - sf
            text = CTRL.sub("", cue_text(c, script, casing, max_chars))
            comp = build_composition(tpl_hex, text=text, frames=frames, width=width, height=height,
                                     fps_value=fps_value, style=style)
            el = clip_tpl
            el = re.sub(r"<Start>\d+</Start>", f"<Start>{base + sf}</Start>", el, count=1)
            el = re.sub(r"<Duration>\d+</Duration>", f"<Duration>{frames}</Duration>", el, count=1)
            el = re.sub(BLOB % "CompositionBA", f"<CompositionBA>{comp}</CompositionBA>", el, count=1)
            el = re.sub(r'DbId="[0-9a-f-]{36}"', lambda m: f'DbId="{uuid.uuid4()}"', el)
            el = re.sub(r"<MediaFrameRate>[0-9a-f]+</MediaFrameRate>",
                        f"<MediaFrameRate>{struct.pack('<dd', fps_value, 0.0).hex()}</MediaFrameRate>", el, count=1)
            out.append(el)
        files[SEQ_PATH] = (seq[:a] + "\n".join(out) + seq[last_end:]).encode("utf-8")

        mp = files[MP_PATH].decode("utf-8")
        files[MP_PATH] = _patch_mp(mp, width, height, fps_value, nominal, spans[-1][2]).encode("utf-8")
        proj = files[PROJECT_PATH].decode("utf-8")
        old = struct.pack(">I", TPL_FPS).hex()
        for m in re.finditer(BLOB % "FieldsBlob", proj):
            raw = bytes.fromhex(m.group(2))
            if len(raw) == 88 and raw[52:56] == bytes.fromhex(old):
                new = raw[:52] + struct.pack(">I", nominal) + raw[56:]
                proj = proj.replace(m.group(2), new.hex(), 1)
                break
        files[PROJECT_PATH] = proj.encode("utf-8")
    except (ValueError, AssertionError, KeyError, AttributeError) as e:  # template layout not as expected
        raise AppError("EXPORT_FAILED", "Could not build the Resolve timeline file.", str(e), 500)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()
