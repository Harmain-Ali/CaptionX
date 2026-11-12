from app.config import Settings
from app.romanize import _parse, clean_roman, fallback_romanize, LLMFormatError
from app.segmenter import Cue, align_roman_words, build_cues, normalize_timing
from app.srt import fmt_time, to_srt, to_vtt, wrap_balanced
from app.transcribe import Seg, Word, filter_hallucinations
import pytest


def seg(text, start, end, words=None, **kw):
    return Seg(text=text, start=start, end=end, words=words or [], **kw)


def test_fmt_time_rounds_not_truncates():
    assert fmt_time(1.9996) == "00:00:02,000"
    assert fmt_time(3661.5) == "01:01:01,500"
    assert fmt_time(-3) == "00:00:00,000"
    assert fmt_time(1.5, vtt=True) == "00:00:01.500"


def test_wrap_balanced():
    assert wrap_balanced("short line", 32) == "short line"
    out = wrap_balanced("this is a much longer caption line here", 20)
    assert out.count("\n") == 1
    assert wrap_balanced("verylongwordwithoutspaces" * 3, 10).count("\n") == 0


def test_build_cues_splits_long_segments_evenly_and_respects_gaps():
    s = Settings(max_words_per_cue=4, max_cue_seconds=10)
    words = [Word(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)]
    cues = build_cues([seg(" ".join(w.text for w in words), 0, 3, words)], s)
    assert [len(c.urdu.split()) for c in cues] == [3, 3, 3]  # balanced, no orphan word
    # a long pause forces a break
    words = [Word("a", 0, 0.3), Word("b", 0.3, 0.6), Word("c", 3.0, 3.3)]
    cues = build_cues([seg("a b c", 0, 3.3, words)], Settings(max_words_per_cue=6))
    assert len(cues) == 2


def test_sentence_end_breaks():
    words = [Word("a", 0, .3), Word("b۔", .3, .6), Word("c", .6, .9), Word("d", .9, 1.2)]
    cues = build_cues([seg("a b۔ c d", 0, 1.2, words)], Settings())
    assert len(cues) == 2 and cues[0].urdu == "a b۔"


def test_segment_without_words_gets_synthesized_timing():
    cues = build_cues([seg("one two three four", 1.0, 3.0)], Settings(max_words_per_cue=6))
    assert len(cues) == 1 and cues[0].uw[0]["s"] == 1.0


def test_timing_never_overlaps_and_min_duration():
    s = Settings(min_cue_seconds=0.5, linger_ms=100)
    cues = [Cue(1, 0.0, 2.0, "a"), Cue(2, 1.5, 1.6, "b"), Cue(3, 1.6, 1.62, "c")]
    normalize_timing(cues, s)
    for a, b in zip(cues, cues[1:]):
        assert a.end <= b.start + 1e-9
    assert all(c.end > c.start for c in cues)


def test_align_roman_words_exact_and_estimated():
    c = Cue(1, 0, 2, "ا ب ج", uw=[{"t": "ا", "s": 0, "e": .5}, {"t": "ب", "s": .5, "e": 1}, {"t": "ج", "s": 1, "e": 1.5}],
            roman="a b j")
    align_roman_words(c)
    assert [w["est"] for w in c.words] == [False] * 3 and c.words[1]["s"] == .5
    c.roman = "ab j"
    align_roman_words(c)
    assert all(w["est"] for w in c.words) and c.words[0]["s"] == 0 and abs(c.words[-1]["e"] - 1.5) < 1e-6


def test_filter_hallucinations():
    segs = [seg("ٹھیک ہے", 0, 1, no_speech_prob=.1, avg_logprob=-.2, compression_ratio=1.1),
            seg("شکریہ", 1, 2, no_speech_prob=.9, avg_logprob=-1.5, compression_ratio=1.0),   # silence
            seg("ہاہاہاہا" * 10, 2, 3, compression_ratio=3.0),                                 # repetition
            seg("", 3, 4),
            *[seg("وہی بات", 4 + i, 5 + i) for i in range(5)]]                                # loop
    kept, dropped = filter_hallucinations(segs)
    texts = [k.text for k in kept]
    assert texts == ["ٹھیک ہے", "وہی بات", "وہی بات"]
    assert dropped == 2 + 3


def test_parse_variants_and_errors():
    assert _parse('{"cues":[{"id":1,"roman":"a"},{"id":2,"roman":"b"}]}', [1, 2]) == {1: "a", 2: "b"}
    assert _parse('<think>hm</think>```json\n{"cues":{"1":"a"}}\n```', [1]) == {1: "a"}
    with pytest.raises(LLMFormatError):
        _parse("nope", [1])
    with pytest.raises(LLMFormatError):
        _parse('{"cues":[{"id":1,"roman":"a"}]}', [1, 2])


def test_clean_roman():
    s = Settings()
    assert clean_roman('  "aaj ہم" ', s) == "aaj ہم"  # script check happens elsewhere
    assert clean_roman("۱۲۳ log، kya؟", s) == "123 log, kya?"
    assert clean_roman("kya, hai?!", Settings(strip_punctuation=True)) == "kya hai"


def test_fallback_romanize_is_latin_and_keeps_digits():
    out = fallback_romanize("آج ۳ لوگ آئے۔")
    assert out.isascii() and "3" in out


def test_srt_vtt_and_offset():
    cues = [Cue(1, 0.0, 1.0, "ا", roman="Hello ji"), Cue(2, 1.2, 2.0, "ب", roman="kya hal hain tum sab ko")]
    out = to_srt(cues, offset_ms=500, casing="uppercase", max_chars=12)
    assert "00:00:00,500 --> 00:00:01,500" in out and "HELLO JI" in out
    assert "KYA HAL HAIN\nTUM SAB KO" in out or "\n" in out.split("00:00:01,700 --> 00:00:02,500\n")[1]
    # negative offset drops cues that end before 0
    neg = to_srt(cues, offset_ms=-1500)
    assert neg.startswith("1\n") and "kya hal hain" in neg and "Hello" not in neg
    assert to_vtt(cues).startswith("WEBVTT")
    # empty roman falls back to the source text, never an empty caption
    assert "ا" in to_srt([Cue(1, 0, 1, "ا", roman="")])
