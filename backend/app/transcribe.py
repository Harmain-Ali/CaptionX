"""Step 1: Groq Whisper -> timestamped segments + words (original script)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional

from .audio import Chunk
from .config import Settings
from .groq_client import call_with_retry


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Seg:
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)
    no_speech_prob: Optional[float] = None
    avg_logprob: Optional[float] = None
    compression_ratio: Optional[float] = None
    dropped: Optional[str] = None  # reason if filtered as hallucination

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Seg":
        words = [Word(**w) for w in d.get("words", [])]
        return Seg(**{**d, "words": words})


def _get(obj: Any, key: str, default=None):
    """The SDK returns extra JSON fields either as dict items or via model_extra."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    v = getattr(obj, key, None)
    if v is None:
        extra = getattr(obj, "model_extra", None) or {}
        v = extra.get(key)
    return default if v is None else v


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def transcribe_chunk(
    client, chunk: Chunk, s: Settings,
    cancel: Optional[Callable[[], None]] = None,
    on_wait: Optional[Callable[[str], None]] = None,
) -> list[Seg]:
    data = chunk.path.read_bytes()

    def _call():
        kwargs: dict[str, Any] = dict(
            file=(chunk.path.name, data),
            model=s.stt_model,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            temperature=s.stt_temperature,
        )
        if s.stt_language and s.stt_language != "auto":
            kwargs["language"] = s.stt_language
        if s.stt_prompt.strip():
            kwargs["prompt"] = s.stt_prompt.strip()
        return client.audio.transcriptions.create(**kwargs)

    resp = call_with_retry(_call, retries=s.max_retries, stage="transcribe", cancel=cancel, on_wait=on_wait)

    raw_segments = _get(resp, "segments", []) or []
    raw_words = _get(resp, "words", []) or []

    segs: list[Seg] = []
    for rs in raw_segments:
        segs.append(Seg(
            text=str(_get(rs, "text", "")).strip(),
            start=_f(_get(rs, "start")) + chunk.offset,
            end=_f(_get(rs, "end")) + chunk.offset,
            no_speech_prob=_get(rs, "no_speech_prob"),
            avg_logprob=_get(rs, "avg_logprob"),
            compression_ratio=_get(rs, "compression_ratio"),
        ))

    # Some responses only contain the plain text (e.g. very short clips): make one segment.
    if not segs:
        text = str(_get(resp, "text", "")).strip()
        if text:
            segs.append(Seg(text=text, start=chunk.offset, end=chunk.offset + chunk.duration))

    words = [Word(str(_get(w, "word", _get(w, "text", ""))).strip(),
                  _f(_get(w, "start")) + chunk.offset, _f(_get(w, "end")) + chunk.offset)
             for w in raw_words]
    words = [w for w in words if w.text]

    # Attach every word to the segment that contains its midpoint (nearest one as fallback).
    if segs and words:
        for w in words:
            mid = (w.start + w.end) / 2
            best = min(segs, key=lambda sg: 0 if sg.start - 0.05 <= mid <= sg.end + 0.05
                       else min(abs(mid - sg.start), abs(mid - sg.end)))
            best.words.append(w)
    return segs


_NORM = re.compile(r"[\s\W_]+", re.UNICODE)


def filter_hallucinations(segs: list[Seg]) -> tuple[list[Seg], int]:
    """Drop the classic Whisper failure modes: phantom text over silence and repetition loops."""
    kept: list[Seg] = []
    dropped = 0
    last_norm, run = None, 0
    for sg in segs:
        norm = _NORM.sub("", sg.text.lower())
        reason = None
        if not norm:
            reason = "empty"
        elif sg.compression_ratio is not None and _f(sg.compression_ratio) > 2.4:
            reason = "repetition"
        elif (sg.no_speech_prob is not None and sg.avg_logprob is not None
              and _f(sg.no_speech_prob) > 0.6 and _f(sg.avg_logprob) < -1.0):
            reason = "silence"
        if reason is None:
            run = run + 1 if norm == last_norm else 1
            last_norm = norm
            if run >= 3:
                reason = "loop"
        if reason:
            sg.dropped = reason
            dropped += 1
            if reason == "empty":
                dropped -= 1  # empty segments are not worth a warning
            continue
        kept.append(sg)
    return kept, dropped
