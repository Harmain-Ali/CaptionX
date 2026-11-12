"""Step 2: shape Whisper segments into short, readable caption cues + clean up timings."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .config import Settings
from .transcribe import Seg, Word

SENTENCE_END = ("۔", ".", "?", "؟", "!", "…")


@dataclass
class Cue:
    index: int
    start: float
    end: float
    urdu: str
    uw: list[dict] = field(default_factory=list)       # source words {t,s,e}
    roman: str = ""
    words: list[dict] = field(default_factory=list)    # roman words {t,s,e,est}
    flags: list[str] = field(default_factory=list)     # fallback | check | edited
    seg: int = 0

    def to_dict(self, public: bool = False) -> dict:
        d = {"index": self.index, "start": round(self.start, 3), "end": round(self.end, 3),
             "urdu": self.urdu, "roman": self.roman, "words": self.words, "flags": self.flags}
        if not public:
            d["uw"] = self.uw
            d["seg"] = self.seg
        return d

    @staticmethod
    def from_dict(d: dict) -> "Cue":
        return Cue(index=d["index"], start=d["start"], end=d["end"], urdu=d.get("urdu", ""),
                   uw=d.get("uw", []), roman=d.get("roman", ""), words=d.get("words", []),
                   flags=d.get("flags", []), seg=d.get("seg", 0))


def _synthesize_words(seg: Seg) -> list[Word]:
    """No word timestamps from the API: spread the segment time over the words by length."""
    tokens = seg.text.split()
    if not tokens:
        return []
    weights = [len(t) + 1 for t in tokens]
    total = sum(weights)
    dur = max(seg.end - seg.start, 0.05)
    out, t = [], seg.start
    for tok, w in zip(tokens, weights):
        d = dur * w / total
        out.append(Word(tok, t, t + d))
        t += d
    return out


def _split_evenly(words: list[Word], k: int) -> list[list[Word]]:
    n = len(words)
    base, extra = divmod(n, k)
    out, i = [], 0
    for j in range(k):
        size = base + (1 if j < extra else 0)
        out.append(words[i:i + size])
        i += size
    return [p for p in out if p]


def build_cues(segs: list[Seg], s: Settings) -> list[Cue]:
    cues: list[Cue] = []
    for si, seg in enumerate(segs):
        words = [w for w in seg.words if w.text] or _synthesize_words(seg)
        if not words:
            continue
        # 1) hard breaks: long pauses and sentence ends
        spans: list[list[Word]] = [[]]
        for i, w in enumerate(words):
            if spans[-1]:
                prev = spans[-1][-1]
                if (w.start - prev.end) > s.gap_break_seconds or prev.text.endswith(SENTENCE_END):
                    spans.append([])
            spans[-1].append(w)
        # 2) split each span into evenly sized cues
        for span in spans:
            n = len(span)
            dur = max(span[-1].end - span[0].start, 0.01)
            k = max(math.ceil(n / s.max_words_per_cue), math.ceil(dur / s.max_cue_seconds), 1)
            k = min(k, n)
            for part in _split_evenly(span, k):
                cues.append(Cue(
                    index=0, start=part[0].start, end=part[-1].end,
                    urdu=" ".join(w.text for w in part),
                    uw=[{"t": w.text, "s": round(w.start, 3), "e": round(w.end, 3)} for w in part],
                    seg=si))
    normalize_timing(cues, s)
    for i, c in enumerate(cues, start=1):
        c.index = i
    return cues


def normalize_timing(cues: list[Cue], s: Settings) -> None:
    """No overlaps, no zero-length cues, readable minimum duration, small linger."""
    cues.sort(key=lambda c: c.start)
    min_gap = 0.02
    for i, c in enumerate(cues):
        c.start = max(c.start, 0.0)
        c.end = max(c.end, c.start + 0.05)
        nxt: Optional[Cue] = cues[i + 1] if i + 1 < len(cues) else None
        if nxt is not None:
            if c.end > nxt.start:
                c.end = max(c.start + 0.05, nxt.start)
            if nxt.start < c.end:           # still overlapping: push the next cue
                nxt.start = c.end
                nxt.end = max(nxt.end, nxt.start + 0.05)
        limit = (nxt.start - min_gap) if nxt is not None else float("inf")
        if c.end - c.start < s.min_cue_seconds:
            c.end = max(c.end, min(c.start + s.min_cue_seconds, limit))
        c.end = max(c.end, min(c.end + s.linger_ms / 1000.0, limit))


def align_roman_words(c: Cue) -> None:
    """Give each roman word a time so the preview can highlight word by word.

    Same word count as the source -> use the real Whisper word times.
    Otherwise estimate by spreading the spoken span proportionally to word length."""
    tokens = c.roman.split()
    c.words = []
    if not tokens:
        return
    if c.uw and len(tokens) == len(c.uw):
        c.words = [{"t": t, "s": u["s"], "e": u["e"], "est": False} for t, u in zip(tokens, c.uw)]
        return
    if c.uw:
        s0, e0 = c.uw[0]["s"], c.uw[-1]["e"]
    else:
        s0, e0 = c.start, c.end
    weights = [len(t) + 1 for t in tokens]
    total, dur, t = sum(weights), max(e0 - s0, 0.05), s0
    for tok, w in zip(tokens, weights):
        d = dur * w / total
        c.words.append({"t": tok, "s": round(t, 3), "e": round(t + d, 3), "est": True})
        t += d
