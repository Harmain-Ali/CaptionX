"""Step 3: Urdu script -> Roman Urdu with a Groq LLM, with validation, retries and a fallback."""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from .config import Settings
from .errors import AppError
from .groq_client import call_with_retry
from .prompts import build_system_prompt
from .segmenter import Cue, align_roman_words

NON_LATIN = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿ऀ-ॿ]")
THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
DIGITS = {ord(a): str(i) for i, a in enumerate("۰۱۲۳۴۵۶۷۸۹")}
DIGITS.update({ord(a): str(i) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")})


class LLMFormatError(Exception):
    pass


# --------------------------------------------------------------------------- fallback
_LETTERS = {
    "ا": "a", "آ": "aa", "ب": "b", "پ": "p", "ت": "t", "ٹ": "t", "ث": "s", "ج": "j", "چ": "ch",
    "ح": "h", "خ": "kh", "د": "d", "ڈ": "d", "ذ": "z", "ر": "r", "ڑ": "r", "ز": "z", "ژ": "zh",
    "س": "s", "ش": "sh", "ص": "s", "ض": "z", "ط": "t", "ظ": "z", "ع": "", "غ": "gh", "ف": "f",
    "ق": "q", "ک": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n", "ں": "n", "و": "o", "ہ": "h",
    "ھ": "h", "ء": "", "ی": "i", "ے": "e", "ئ": "i", "ۃ": "h", "ؤ": "o", "ي": "i", "ك": "k",
    "ە": "h", "ۓ": "e", "ۂ": "h", "،": ",", "۔": ".", "؟": "?", "؛": ";",
}
_STRIP = dict.fromkeys(map(ord, "ًٌٍَُِّْٰ‌‍‎‏"), None)


def fallback_romanize(text: str) -> str:
    """Very rough letter-by-letter mapping. Only used when the LLM failed for a cue."""
    text = text.translate(_STRIP).translate(DIGITS)
    return "".join(_LETTERS.get(ch, ch) for ch in text).strip()


# --------------------------------------------------------------------------- helpers
def clean_roman(text: str, s: Settings) -> str:
    t = text.translate(DIGITS).strip()
    t = re.sub(r"^```\w*|```$", "", t).strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'“”":
        t = t[1:-1].strip()
    t = t.replace("،", ",").replace("۔", ".").replace("؟", "?")
    if s.strip_punctuation:
        t = re.sub(r"[.,!?;:…\"“”()\[\]]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _extract_json(content: str) -> dict:
    content = THINK.sub("", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise LLMFormatError("response was not valid JSON")


def _parse(content: str, ids: list[int]) -> dict[int, str]:
    data = _extract_json(content)
    items = data.get("cues") if isinstance(data, dict) else data
    out: dict[int, str] = {}
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and "id" in it:
                try:
                    out[int(it["id"])] = str(it.get("roman", it.get("text", "")))
                except (TypeError, ValueError):
                    continue
    elif isinstance(items, dict):  # {"1": "...", "2": "..."}
        for k, v in items.items():
            try:
                out[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
    missing = [i for i in ids if i not in out]
    if missing:
        raise LLMFormatError(f"missing ids {missing[:5]}")
    return {i: out[i] for i in ids}


def _problem(cue: Cue, roman: str) -> Optional[str]:
    """None = fine, 'length' = accept but flag, anything else = retry."""
    if cue.urdu.strip() and not roman.strip():
        return "empty"
    if NON_LATIN.search(roman):
        return "script"
    n_in, n_out = len(cue.urdu.split()), len(roman.split())
    if n_in >= 3 and not (0.4 * n_in <= n_out <= 2.5 * n_in):
        return "length"
    return None


# --------------------------------------------------------------------------- main class
class Romanizer:
    def __init__(self, client, s: Settings, cancel: Optional[Callable[[], None]] = None,
                 on_message: Optional[Callable[[str], None]] = None):
        self.client, self.s, self.cancel, self.on_message = client, s, cancel, on_message
        self.system_prompt = build_system_prompt(s)
        self._json_mode = True

    # -- LLM call ------------------------------------------------------------
    def _ask(self, cues: list[Cue], ctx: str, temperature: float) -> dict[int, str]:
        payload = json.dumps(
            {"context_before": ctx, "cues": [{"id": c.index, "text": c.urdu} for c in cues]},
            ensure_ascii=False)

        def _call():
            kwargs = dict(
                model=self.s.llm_model,
                messages=[{"role": "system", "content": self.system_prompt},
                          {"role": "user", "content": payload}],
                temperature=temperature,
                max_tokens=self.s.llm_max_tokens,
            )
            if self._json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if "gpt-oss" in self.s.llm_model:
                kwargs["reasoning_effort"] = "low"  # transliteration needs no deep thinking: faster, fewer tokens
            return self.client.chat.completions.create(**kwargs)

        try:
            resp = call_with_retry(_call, retries=self.s.max_retries, stage="romanize",
                                   cancel=self.cancel, on_wait=self.on_message)
        except AppError as e:
            if e.code == "LLM_JSON_INVALID":
                if self._json_mode:
                    # Groq's strict JSON mode rejected the reply (some models, e.g. gpt-oss, trip on it).
                    # Ask in plain text instead; _parse() already extracts the JSON from free text.
                    self._json_mode = False
                    return self._ask(cues, ctx, temperature)
                raise LLMFormatError(e.message)
            if e.code == "BAD_REQUEST" and "response_format" in e.message.lower() and self._json_mode:
                self._json_mode = False  # this model has no JSON mode: ask in plain text
                return self._ask(cues, ctx, temperature)
            raise
        content = (resp.choices[0].message.content or "") if resp.choices else ""
        if getattr(resp.choices[0], "finish_reason", None) == "length":
            raise LLMFormatError("response was cut off (max tokens too low)")
        return _parse(content, [c.index for c in cues])

    # -- recursion: shrink the batch until it works --------------------------
    def _apply(self, cue: Cue, roman: str, flag: Optional[str] = None) -> None:
        cue.roman = clean_roman(roman, self.s)
        if flag and flag not in cue.flags:
            cue.flags.append(flag)
        align_roman_words(cue)

    def _process(self, cues: list[Cue], ctx: str) -> None:
        attempts = 2 if len(cues) == 1 else 1
        out = None
        for a in range(attempts):
            try:
                out = self._ask(cues, ctx, self.s.llm_temperature if a == 0 else min(0.4, self.s.llm_temperature + 0.3))
                break
            except LLMFormatError:
                out = None
        if out is None:
            if len(cues) == 1:
                self._apply(cues[0], fallback_romanize(cues[0].urdu), "fallback")
                return
            mid = len(cues) // 2
            self._process(cues[:mid], ctx)
            self._process(cues[mid:], cues[mid - 1].urdu)
            return

        bad: list[Cue] = []
        for c in cues:
            roman = clean_roman(out[c.index], self.s)
            p = _problem(c, roman)
            if p is None:
                self._apply(c, roman)
            elif p == "length":
                self._apply(c, roman, "check")
            else:
                bad.append(c)
        if not bad:
            return
        if len(bad) == len(cues) and len(cues) == 1:
            self._apply(bad[0], fallback_romanize(bad[0].urdu), "fallback")
        elif len(bad) == len(cues):
            mid = len(bad) // 2
            self._process(bad[:mid], ctx)
            self._process(bad[mid:], bad[mid - 1].urdu)
        else:
            self._process(bad, ctx)

    def run(self, cues: list[Cue], on_progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Romanize whole phrases (one per Whisper segment), then split the result back onto the cues.

        Sending one-word cues individually multiplies requests and repeats the long system prompt every
        time, which hits Groq's per-minute token limits. Phrases are also spelled better than lone words."""
        groups: list[list[Cue]] = []
        for c in cues:
            if groups and groups[-1][0].seg == c.seg:
                groups[-1].append(c)
            else:
                groups.append([c])
        phrases = [
            Cue(index=i, start=g[0].start, end=g[-1].end, urdu=" ".join(c.urdu for c in g),
                uw=[w for c in g for w in c.uw], seg=g[0].seg)
            for i, g in enumerate(groups, start=1)
        ]
        size = max(1, self.s.llm_batch_size)
        batches = [phrases[i:i + size] for i in range(0, len(phrases), size)]
        ctx = ""
        for bi, batch in enumerate(batches):
            if self.cancel:
                self.cancel()
            if on_progress:
                on_progress(bi, len(batches))
            self._process(batch, ctx)
            ctx = batch[-1].urdu
        for g, ph in zip(groups, phrases):
            self._distribute(g, ph)
        if on_progress:
            on_progress(len(batches), len(batches))

    def _distribute(self, group: list[Cue], phrase: Cue) -> None:
        """Hand the phrase's Roman words back to the cues it was built from, in order."""
        flags = [f for f in phrase.flags if f in ("fallback", "check")]
        if len(group) == 1:
            c = group[0]
            c.roman = phrase.roman
            c.flags += [f for f in flags if f not in c.flags]
            align_roman_words(c)
            return
        tokens = phrase.roman.split()
        counts = [max(len(c.uw) or len(c.urdu.split()), 1) for c in group]
        total, n = sum(counts), len(tokens)
        cum, bounds = 0, []
        for k in counts:
            cum += k
            bounds.append(n if cum == total else round(n * cum / total))  # exact when word counts match
        prev = 0
        for i, c in enumerate(group):
            if n >= len(group):  # every cue gets at least one word, and the last one gets the rest
                end = n if i == len(group) - 1 else min(max(bounds[i], prev + 1), n - (len(group) - 1 - i))
            else:
                end = min(bounds[i], n)
            c.roman = " ".join(tokens[prev:end])
            prev = end
            if not c.roman:  # fewer Roman words than cues: spell this one offline and flag it
                c.roman = fallback_romanize(c.urdu)
                flags_i = flags + ["check"]
            else:
                flags_i = flags
            c.flags += [f for f in flags_i if f not in c.flags]
            align_roman_words(c)
