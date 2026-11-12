"""SRT / WebVTT / TXT writers. Casing, offset and line wrapping are applied here at export time."""
from __future__ import annotations

import re
from typing import Iterable

from .segmenter import Cue


def fmt_time(seconds: float, vtt: bool = False) -> str:
    ms_total = max(0, int(round(seconds * 1000)))  # round, don't truncate
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    sep = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def apply_casing(text: str, casing: str) -> str:
    if casing == "lowercase":
        return text.lower()
    if casing == "uppercase":
        return text.upper()
    return text


def wrap_balanced(text: str, max_chars: int) -> str:
    """At most 2 lines, split at the space closest to the middle."""
    text = text.strip()
    if max_chars <= 0 or len(text) <= max_chars or " " not in text:
        return text
    mid = len(text) / 2
    best, best_dist = None, 1e9
    for m in re.finditer(" ", text):
        d = abs(m.start() - mid)
        if d < best_dist:
            best, best_dist = m.start(), d
    return text[:best] + "\n" + text[best + 1:]


def _clean(text: str) -> str:
    text = text.replace("-->", "->")
    text = re.sub(r"\n\s*\n+", "\n", text).strip()  # a blank line would end the cue in SRT
    return text


def cue_text(c: Cue, script: str, casing: str, max_chars: int) -> str:
    roman = apply_casing(c.roman.strip(), casing)
    urdu = c.urdu.strip()
    if script == "urdu":
        body = urdu
    elif script == "both":
        body = wrap_balanced(roman or urdu, max_chars) + ("\n" + urdu if urdu else "")
    else:
        body = wrap_balanced(roman or urdu, max_chars)  # never export an empty caption
    return _clean(body)


def _shifted(cues: Iterable[Cue], offset_ms: int):
    off = offset_ms / 1000.0
    for c in cues:
        s, e = c.start + off, c.end + off
        if e <= 0:
            continue  # shifted completely before 0:00
        yield c, max(s, 0.0), e


def to_srt(cues: list[Cue], offset_ms: int = 0, casing: str = "natural",
           max_chars: int = 32, script: str = "roman") -> str:
    out = []
    for n, (c, s, e) in enumerate(_shifted(cues, offset_ms), start=1):
        out.append(f"{n}\n{fmt_time(s)} --> {fmt_time(e)}\n{cue_text(c, script, casing, max_chars)}\n")
    return "\n".join(out)


def to_vtt(cues: list[Cue], offset_ms: int = 0, casing: str = "natural",
           max_chars: int = 32, script: str = "roman") -> str:
    out = ["WEBVTT\n"]
    for c, s, e in _shifted(cues, offset_ms):
        out.append(f"{fmt_time(s, True)} --> {fmt_time(e, True)}\n{cue_text(c, script, casing, max_chars)}\n")
    return "\n".join(out)


def to_txt(cues: list[Cue], casing: str = "natural", script: str = "roman") -> str:
    return "\n".join(cue_text(c, script, casing, 0).replace("\n", " ") for c in cues) + "\n"
