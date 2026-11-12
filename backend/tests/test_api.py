import pytest
import re
from pathlib import Path

import groq

from app.config import store
from conftest import groq_error, make_media, upload, wait_job

SRT_BLOCK = re.compile(r"^\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n.+", re.M)


def to_secs(t):
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def test_happy_path_end_to_end(tmp_path, client, fake):
    wav = make_media(tmp_path / "reel.wav")
    r = upload(client, wav)
    assert r.status_code == 202
    jid = r.json()["id"]
    job = wait_job(client, jid)
    assert job["status"] == "done", job
    assert job["cue_count"] >= 2 and job["has_preview"] and job["has_transcript"]
    assert fake.stt_calls == 1 and fake.llm_calls == 1  # whole reel = one LLM request
    cues = job["cues"]
    assert all(c["roman"].isascii() and c["roman"] for c in cues)
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(cues, cues[1:]))
    assert all(c["words"] for c in cues)

    srt = client.get(f"/api/jobs/{jid}/export?format=srt")
    assert srt.status_code == 200 and "attachment" in srt.headers["content-disposition"]
    assert len(SRT_BLOCK.findall(srt.text)) == len(cues)
    # timestamps are monotonic in the exported file
    starts = [to_secs(m) for m in re.findall(r"^(\d\d:\d\d:\d\d,\d{3}) -->", srt.text, re.M)]
    assert starts == sorted(starts)

    off = client.get(f"/api/jobs/{jid}/export?format=srt&offset_ms=1000").text
    assert "00:00:01," in off.split("\n")[1]
    assert client.get(f"/api/jobs/{jid}/export?format=vtt").text.startswith("WEBVTT")
    both = client.get(f"/api/jobs/{jid}/export?format=srt&script=both").text
    assert "السلام" in both
    assert client.get(f"/api/jobs/{jid}/export?format=txt").status_code == 200

    # audio supports Range requests (needed for seeking in the preview player)
    full = client.get(f"/api/jobs/{jid}/audio")
    assert full.status_code == 200 and full.headers["content-type"].startswith("audio/mpeg")
    part = client.get(f"/api/jobs/{jid}/audio", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100


def test_edit_cues_and_options(tmp_path, client, fake):
    jid = upload(client, make_media(tmp_path / "a.wav")).json()["id"]
    job = wait_job(client, jid)
    r = client.put(f"/api/jobs/{jid}/cues", json={"edits": [{"index": 1, "roman": "Assalam o alaikum dosto"}]})
    assert r.status_code == 200
    c1 = r.json()["cues"][0]
    assert c1["roman"] == "Assalam o alaikum dosto" and "edited" in c1["flags"] and len(c1["words"]) == 4
    assert client.put(f"/api/jobs/{jid}/cues", json={"edits": [{"index": 99, "roman": "x"}]}).status_code == 422
    client.put(f"/api/jobs/{jid}/options", json={"offset_ms": -250, "casing": "uppercase"})
    assert client.get(f"/api/jobs/{jid}").json()["offset_ms"] == -250
    assert "ASSALAM O ALAIKUM DOSTO" in client.get(f"/api/jobs/{jid}/export").text
    assert client.put(f"/api/jobs/{jid}/options", json={"offset_ms": 999999}).status_code == 422


def test_reprocess_reuses_transcript(tmp_path, client, fake):
    jid = upload(client, make_media(tmp_path / "a.wav")).json()["id"]
    wait_job(client, jid)
    stt_before = fake.stt_calls
    r = client.post(f"/api/jobs/{jid}/reprocess", json={"overrides": {"max_words_per_cue": 2, "casing": "lowercase"}})
    assert r.status_code == 202
    job = wait_job(client, jid)
    assert job["status"] == "done" and fake.stt_calls == stt_before  # no new Whisper call
    assert max(len(c["urdu"].split()) for c in job["cues"]) <= 2
    assert client.post(f"/api/jobs/{jid}/reprocess", json={"overrides": {"max_words_per_cue": 0}}).status_code == 422


def test_missing_key_is_rejected_before_upload(tmp_path, client, monkeypatch):
    store.reset(keep_key=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = upload(client, make_media(tmp_path / "a.wav"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "MISSING_API_KEY"


def test_upload_validation(tmp_path, client, fake):
    bad = tmp_path / "doc.pdf"
    bad.write_bytes(b"%PDF")
    assert upload(client, bad).json()["error"]["code"] == "UNSUPPORTED_MEDIA"
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    r = upload(client, empty)
    assert r.status_code == 422 and r.json()["error"]["code"] == "EMPTY_FILE"
    assert client.get("/api/jobs").json()["jobs"] == [] or all(j["filename"] != "empty.mp3" for j in client.get("/api/jobs").json()["jobs"])
    store.update({"max_upload_mb": 1})
    big = tmp_path / "big.wav"
    big.write_bytes(b"0" * (2 * 1024 * 1024))
    r = upload(client, big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE"
    store.update({"max_upload_mb": 500})
    r = upload(client, tmp_path / "doc.pdf", {"max_words_per_cue": 9999})
    assert r.status_code == 422


def test_corrupt_media(tmp_path, client, fake):
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"this is not audio at all" * 100)
    job = wait_job(client, upload(client, junk).json()["id"])
    assert job["status"] == "error" and job["error"]["code"] == "UNSUPPORTED_MEDIA"
    assert fake.stt_calls == 0


def test_no_audio_stream_and_silence(tmp_path, client, fake):
    vid = make_media(tmp_path / "v.mp4", "video_no_audio", 2)
    assert wait_job(client, upload(client, vid).json()["id"])["error"]["code"] == "NO_AUDIO_STREAM"
    sil = make_media(tmp_path / "s.wav", "silence", 3)
    job = wait_job(client, upload(client, sil).json()["id"])
    assert job["error"]["code"] == "NO_SPEECH" and fake.stt_calls == 0  # never wastes a Whisper call


def test_too_long(tmp_path, client, fake):
    store.update({"max_duration_minutes": 1})
    wav = make_media(tmp_path / "long.wav", seconds=70)
    assert wait_job(client, upload(client, wav).json()["id"])["error"]["code"] == "TOO_LONG"
    store.update({"max_duration_minutes": 60})


def test_whisper_returns_nothing(tmp_path, client, fake):
    from types import SimpleNamespace
    fake.stt_response = lambda kw: SimpleNamespace(text="", segments=[], words=[])
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["error"]["code"] == "NO_SPEECH" and job["error"]["stage"] == "segment"


def test_whisper_text_only_still_works(tmp_path, client, fake):
    from types import SimpleNamespace
    fake.stt_response = lambda kw: SimpleNamespace(text="آج ہم بات کریں گے")
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["status"] == "done" and job["cues"][0]["roman"]


def test_chunking_offsets_are_added(tmp_path, client, fake):
    from types import SimpleNamespace
    store.update({"chunk_seconds": 60})
    seen = []

    def stt(kw):
        seen.append(kw["file"][0])
        tail = ["ایک", "دو", "تین"][len(seen) - 1]  # distinct text: identical repeats are filtered as a loop
        return SimpleNamespace(text="x", segments=[{"text": f"آج ہم {tail}", "start": 1.0, "end": 2.0}],
                               words=[{"word": "آج", "start": 1.0, "end": 1.3}, {"word": "ہم", "start": 1.3, "end": 1.6},
                                      {"word": tail, "start": 1.6, "end": 2.0}])

    fake.stt_response = stt
    job = wait_job(client, upload(client, make_media(tmp_path / "long.wav", seconds=130)).json()["id"], timeout=60)
    assert job["status"] == "done" and len(seen) == 3
    starts = [round(c["start"]) for c in job["cues"]]
    assert starts[0] == 1 and 60 <= starts[1] <= 62 and 120 <= starts[2] <= 123  # offsets accumulate
    store.update({"chunk_seconds": 600})


def test_llm_garbage_falls_back_and_flags(tmp_path, client, fake):
    fake.llm_behavior = "garbage"
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["status"] == "done"
    assert all("fallback" in c["flags"] and c["roman"].isascii() for c in job["cues"])
    assert any("fallback" in w for w in job["warnings"])


def test_llm_missing_ids_split_and_recover(tmp_path, client, fake):
    fake.llm_behavior = "missing"
    store.update({"max_words_per_cue": 3})
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["status"] == "done" and len(job["cues"]) >= 4
    assert all(c["roman"] for c in job["cues"])  # recursion shrank the batch until it worked
    store.update({"max_words_per_cue": 6})


def test_llm_returns_urdu_script_is_rejected(tmp_path, client, fake):
    fake.llm_behavior = "urdu"
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["status"] == "done"
    assert all("fallback" in c["flags"] and c["roman"].isascii() for c in job["cues"])


def test_invalid_key_surfaces_clearly_and_transcript_is_kept(tmp_path, client, fake):
    fake.llm_behavior = "auth"
    jid = upload(client, make_media(tmp_path / "a.wav")).json()["id"]
    job = wait_job(client, jid)
    assert job["status"] == "error" and job["error"]["code"] == "INVALID_API_KEY"
    assert job["error"]["stage"] == "romanize" and job["has_transcript"]
    # fix the "key", retry only the LLM part
    fake.llm_behavior = "ok"
    assert client.post(f"/api/jobs/{jid}/reprocess", json={"overrides": {}}).status_code == 202
    assert wait_job(client, jid)["status"] == "done"


def test_whisper_errors_are_mapped(tmp_path, client, fake):
    def boom(kw):
        raise groq_error(groq.APIStatusError, 413, "too big")
    fake.stt_response = boom
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["error"]["code"] == "PAYLOAD_TOO_LARGE" and job["error"]["stage"] == "transcribe"


def test_rate_limit_is_retried(tmp_path, client, fake):
    fake.llm_behavior = "ratelimit_once"
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"], timeout=30)
    assert job["status"] == "done" and fake.llm_calls == 2


def test_daily_rate_limit_fails_fast(tmp_path, client, fake):
    def limited(**kw):
        raise groq_error(groq.RateLimitError, 429, "daily tokens", {"retry-after": "3600"})
    fake.chat.completions.create = limited
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["error"]["code"] == "RATE_LIMITED" and "min" in job["error"]["message"]


def test_network_error_after_retries(tmp_path, client, fake):
    import httpx
    store.update({"max_retries": 1})

    def down(kw):
        raise groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))
    fake.stt_response = down
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"], timeout=30)
    assert job["error"]["code"] == "NETWORK_ERROR"
    store.update({"max_retries": 2})


def test_cancel(tmp_path, client, fake):
    import time
    from types import SimpleNamespace
    fake.stt_response = lambda kw: (time.sleep(1.0), SimpleNamespace(text="آج ہم", segments=[], words=[]))[1]
    jid = upload(client, make_media(tmp_path / "a.wav")).json()["id"]
    time.sleep(0.4)
    client.post(f"/api/jobs/{jid}/cancel")
    assert wait_job(client, jid)["status"] == "cancelled"


def test_job_not_found_and_traversal(client):
    assert client.get("/api/jobs/doesnotexist").status_code == 404
    r = client.get("/api/jobs/..%2F..%2Fetc")   # the client normalises this to /etc; with a built UI that is the SPA page
    assert r.status_code in (404, 422) or "text/html" in r.headers["content-type"]
    assert client.get("/api/jobs/a%2Fb/audio").status_code == 404


def test_delete_job(tmp_path, client, fake):
    jid = upload(client, make_media(tmp_path / "a.wav")).json()["id"]
    wait_job(client, jid)
    assert client.delete(f"/api/jobs/{jid}").status_code == 200
    assert client.get(f"/api/jobs/{jid}").status_code == 404


def test_settings_api(client, fake):
    s = client.get("/api/settings").json()
    assert "groq_api_key" not in s and s["groq_api_key_set"] and "…" in s["groq_api_key_masked"]
    # masked/empty key never overwrites the real one
    client.put("/api/settings", json={"groq_api_key": s["groq_api_key_masked"], "llm_batch_size": 10})
    client.put("/api/settings", json={"groq_api_key": "  "})
    assert store.get().groq_api_key == "gsk_test_key_123456" and store.get().llm_batch_size == 10
    r = client.put("/api/settings", json={"max_words_per_cue": 0, "linger_ms": 99999})
    assert r.status_code == 422 and set(r.json()["error"]["fields"]) == {"max_words_per_cue", "linger_ms"}
    assert client.put("/api/settings", json={"nonsense": 1}).status_code == 422
    assert client.post("/api/settings/reset").json()["llm_batch_size"] == 25
    assert store.get().groq_api_key  # reset keeps the key
    client.put("/api/settings", json={"clear_api_key": True})
    assert client.get("/api/settings").json()["groq_api_key_set"] is False
    assert "RULES" not in client.get("/api/settings/default-prompt").text
    assert "{{CASING_RULE}}" in client.get("/api/settings/default-prompt").json()["prompt"]


def test_models_and_test_key(client, fake):
    m = client.get("/api/models").json()
    assert m["source"] == "live" and "whisper-large-v3" in m["stt"]
    assert "llama-3.3-70b-versatile" in m["llm"] and not any("guard" in x for x in m["llm"])
    assert client.post("/api/settings/test-key", json={}).json() == {"ok": True, "model_count": 5}
    store.update({"groq_api_key": ""})
    m = client.get("/api/models").json()
    assert m["source"] == "fallback" and m["warning"]
    assert client.post("/api/settings/test-key", json={}).status_code == 400


def test_prompt_builder_applies_settings():
    from app.config import Settings
    from app.prompts import build_system_prompt
    p = build_system_prompt(Settings(glossary="فن => FANN", casing="lowercase", strip_punctuation=True))
    assert "فن => FANN" in p and "{{" not in p and "lowercase" in p and "remove all punctuation" in p
    custom = build_system_prompt(Settings(system_prompt="Only JSON. {{CASING_RULE}}"))
    assert custom.startswith("Only JSON.") and "{{" not in custom


def test_health(client, fake):
    h = client.get("/api/health").json()
    assert h["ok"] and h["ffmpeg"] and h["key_set"]


def test_groq_json_mode_rejection_falls_back_to_plain_text(tmp_path, client, fake):
    fake.llm_behavior = "jsonmode_fail"
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["status"] == "done", job
    assert fake.llm_calls == 2  # one rejected JSON-mode call, one plain-text call
    assert all(c["roman"].isascii() and "fallback" not in c["flags"] for c in job["cues"])


# ------------------------------------------------------------------------------ FCPXML export
def test_fcpxml_export_structure_and_frame_accuracy(tmp_path, client, fake):
    import xml.etree.ElementTree as ET
    from fractions import Fraction

    jid = upload(client, make_media(tmp_path / "reel.wav")).json()["id"]
    job = wait_job(client, jid)
    r = client.get(f"/api/jobs/{jid}/export?format=fcpxml&fps=29.97&resolution=1080x1920")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert ".fcpxml" in r.headers["content-disposition"]
    root = ET.fromstring(r.text)                      # well-formed
    assert root.tag == "fcpxml" and root.get("version") == "1.9"
    fmt = root.find("./resources/format")
    assert fmt.get("frameDuration") == "1001/30000s" and (fmt.get("width"), fmt.get("height")) == ("1080", "1920")
    titles = root.findall(".//gap/title")
    assert len(titles) == job["cue_count"]
    fd = Fraction(1001, 30000)

    def sec(v):
        v = v.rstrip("s")
        return Fraction(v) if "/" in v else Fraction(int(v))
    prev_end = Fraction(0)
    for t in titles:
        off, dur = sec(t.get("offset")), sec(t.get("duration"))
        assert (off / fd).denominator == 1 and (dur / fd).denominator == 1   # whole frames
        assert dur >= fd and off >= prev_end                                 # >=1 frame, no overlap
        prev_end = off + dur
        sid = t.find("text/text-style").get("ref")
        assert t.find(f"text-style-def[@id='{sid}']") is not None
        assert t.find("text/text-style").text.strip()
    assert sec(root.find(".//sequence").get("duration")) == prev_end
    ids = [t.find("text-style-def").get("id") for t in titles]
    assert len(set(ids)) == len(ids)                                          # unique style ids


def test_fcpxml_validation_offset_and_escaping(tmp_path, client, fake):
    import xml.etree.ElementTree as ET
    jid = upload(client, make_media(tmp_path / "a.wav")).json()["id"]
    wait_job(client, jid)
    client.put(f"/api/jobs/{jid}/cues", json={"edits": [{"index": 1, "roman": 'Tom & Jerry <b> "hi"'}]})
    xml = client.get(f"/api/jobs/{jid}/export?format=fcpxml").text
    first = ET.fromstring(xml).find(".//gap/title/text/text-style")
    assert first.text == 'Tom & Jerry <b> "hi"'                               # escaped on write, intact on read
    assert client.get(f"/api/jobs/{jid}/export?format=fcpxml&fps=31").status_code == 422
    assert client.get(f"/api/jobs/{jid}/export?format=fcpxml&resolution=banana").status_code == 422
    # offset moves every title, and a large negative offset never produces a negative time
    late = ET.fromstring(client.get(f"/api/jobs/{jid}/export?format=fcpxml&fps=25&offset_ms=1000").text)
    assert late.find(".//gap/title").get("offset") != "0s"
    early = ET.fromstring(client.get(f"/api/jobs/{jid}/export?format=fcpxml&fps=25&offset_ms=-1500").text)
    assert all(not t.get("offset").startswith("-") for t in early.findall(".//gap/title"))
    # settings feed the style
    client.put("/api/settings", json={"fcpxml_font": "Impact", "fcpxml_font_size": 90, "fcpxml_text_color": "#FFD400"})
    st = ET.fromstring(client.get(f"/api/jobs/{jid}/export?format=fcpxml").text).find(".//text-style-def/text-style")
    assert st.get("font") == "Impact" and st.get("fontSize") == "90" and st.get("fontColor").startswith("1.0000 0.8314")
    assert client.put("/api/settings", json={"fcpxml_text_color": "yellow"}).status_code == 422


# --------------------------------------------------------------- one word per line / rate limits
def test_one_word_per_line_uses_one_llm_request(tmp_path, client, fake):
    store.update({"max_words_per_cue": 1})
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["status"] == "done"
    assert len(job["cues"]) >= 14                                # many one-word lines...
    assert fake.llm_calls == 1                                   # ...but still a single Groq request
    assert all(len(c["urdu"].split()) == 1 and len(c["roman"].split()) == 1 for c in job["cues"])
    assert all(not c["words"][0]["est"] for c in job["cues"])    # exact word timings kept
    store.update({"max_words_per_cue": 6})


def test_phrase_split_when_word_counts_differ(tmp_path, client, fake):
    fake.llm_behavior = "fewer"
    store.update({"max_words_per_cue": 1})
    job = wait_job(client, upload(client, make_media(tmp_path / "a.wav")).json()["id"])
    assert job["status"] == "done"
    assert all(c["roman"].strip() and c["roman"].isascii() for c in job["cues"])   # nobody left empty
    assert fake.llm_calls == 1
    store.update({"max_words_per_cue": 6})


# ------------------------------------------------------------------------------ Fusion Text+ .setting
def _lua():
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        local function ident(t) return t end
        ordered = function() return ident end
        TextPlus, Input, BezierSpline, OperatorInfo, Text, FuID = ident, ident, ident, ident, ident, ident
    """)
    return lua


def test_fusion_setting_parses_as_lua_with_keyframed_text(tmp_path, client, fake):
    lua = _lua()
    store.update({"max_words_per_cue": 1, "fcpxml_font": "Impact", "fcpxml_text_color": "#FFD400", "fcpxml_position_y": 0.7})
    jid = upload(client, make_media(tmp_path / "reel.wav")).json()["id"]
    job = wait_job(client, jid)
    r = client.get(f"/api/jobs/{jid}/export?format=fusion&fps=30&resolution=1080x1920")
    assert r.status_code == 200 and "reel.textplus.setting" in r.headers["content-disposition"]
    tree = lua.eval(r.text)                                    # real Lua parser: any syntax slip raises here
    tool = tree["Tools"]["Captions"]
    ins = tool["Inputs"]
    assert ins["Font"]["Value"] == "Impact" and abs(ins["Center"]["Value"][2] - 0.3) < 1e-9
    assert abs(ins["Red1"]["Value"] - 1.0) < 1e-6 and ins["StyledText"]["SourceOp"] == "CaptionsStyledText"
    kf = tree["Tools"]["CaptionsStyledText"]["KeyFrames"]
    frames = sorted(int(k) for k in kf.keys())
    assert frames[0] == 0 and frames == sorted(set(frames))
    texts = [(f, kf[f]["Value"]["Value"]) for f in frames]
    shown = [t for _, t in texts if t]
    assert len(shown) == job["cue_count"] and all(t.isascii() for t in shown)
    assert texts[-1][1] == ""                                  # the last caption is closed by a blank key
    assert client.get(f"/api/jobs/{jid}/export?format=fusion&fps=31").status_code == 422
    store.update({"max_words_per_cue": 6, "fcpxml_font": "Arial", "fcpxml_text_color": "#FFFFFF"})


def test_fusion_setting_escapes_hostile_text_and_keeps_gaps_blank(tmp_path, client, fake):
    lua = _lua()
    jid = upload(client, make_media(tmp_path / "a.wav")).json()["id"]
    wait_job(client, jid)
    evil = 'He said "hi" \\ it\'s ]] }, Value = 1 --'
    client.put(f"/api/jobs/{jid}/cues", json={"edits": [{"index": 1, "roman": evil}]})
    tree = lua.eval(client.get(f"/api/jobs/{jid}/export?format=fusion&casing=natural").text)
    kf = tree["Tools"]["CaptionsStyledText"]["KeyFrames"]
    values = [kf[k]["Value"]["Value"].replace("\n", " ") for k in sorted(kf.keys(), key=int)]   # wrapping may add a newline
    assert evil in values                                      # survives quotes, backslashes, Lua-ish text
    assert "" in values                                        # silence between captions is blank, not stuck text
    both = lua.eval(client.get(f"/api/jobs/{jid}/export?format=fusion&script=both").text)   # Urdu + newline
    assert any("\n" in kf2["Value"]["Value"] for kf2 in both["Tools"]["CaptionsStyledText"]["KeyFrames"].values())


# ------------------------------------------------------------------------------ Resolve .drt (one Text+ per caption)
def test_drt_has_one_text_plus_clip_per_caption(tmp_path, client, fake):
    import io, re, struct, zipfile
    from app import drt
    store.update({"max_words_per_cue": 1, "fcpxml_font": "Impact", "fcpxml_font_size": 100})
    jid = upload(client, make_media(tmp_path / "reel.wav")).json()["id"]
    job = wait_job(client, jid)
    r = client.get(f"/api/jobs/{jid}/export?format=drt&fps=30&resolution=1080x1920")
    assert r.status_code == 200 and "reel.textplus.drt" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.testzip() is None and {drt.SEQ_PATH, drt.MP_PATH, drt.PROJECT_PATH} <= set(z.namelist())
    import xml.etree.ElementTree as ET
    ET.fromstring(z.read(drt.SEQ_PATH))                       # (Resolve's own project.xml/MpFolder.xml use "A::B" tag names, so they are not strict XML)
    tpl = zipfile.ZipFile(drt.TEMPLATE)
    assert [i.filename for i in z.infolist()] == [i.filename for i in tpl.infolist()]
    seq = z.read(drt.SEQ_PATH).decode()
    clips = re.findall(r"<Sm2TiVideoClip DbId=\"([^\"]+)\">.*?<Start>(\d+)</Start>\s*<Duration>(\d+)</Duration>", seq, re.S)
    assert len(clips) == job["cue_count"] and len({c[0] for c in clips}) == len(clips)
    ids = re.findall(r'DbId="([0-9a-f-]{36})"', seq)
    assert len(ids) == len(set(ids))                          # no duplicate database ids
    starts = [int(c[1]) for c in clips]; durs = [int(c[2]) for c in clips]
    assert starts[0] >= 3600 * 30 and all(starts[i] + durs[i] <= starts[i + 1] for i in range(len(clips) - 1))
    texts = [drt.read_text(h) for h in re.findall(r"<CompositionBA>([0-9a-f]+)</CompositionBA>", seq)]
    assert len(texts) == len(clips) and all(t and t.isascii() for t in texts)
    mp = z.read(drt.MP_PATH).decode()
    assert struct.pack(">qq", 1080, 1920).hex() in mp and struct.pack("<dd", 30.0, 0.0).hex() in mp
    assert client.get(f"/api/jobs/{jid}/export?format=drt&fps=31").status_code == 422
    store.update({"max_words_per_cue": 6, "fcpxml_font": "Arial", "fcpxml_font_size": 72})


def test_drt_composition_roundtrips_hostile_text():
    from app import drt
    import re, zipfile
    from app.config import Settings
    seq = zipfile.ZipFile(drt.TEMPLATE).read(drt.SEQ_PATH).decode()
    tpl = re.findall(r"<CompositionBA>([0-9a-f]+)</CompositionBA>", seq)[0]
    evil = 'He said "hi" \\ it\'s\nline2 }, Value = 1 --'
    h = drt.build_composition(tpl, text=evil, frames=7, width=1080, height=1920, fps_value=29.97, style=Settings())
    assert drt.read_text(h) == evil


# ------------------------------------------------------------------------------ packaging helpers
def test_data_dir_is_per_user_when_packaged(tmp_path):
    from pathlib import Path
    from app import paths
    win = paths.default_data_dir(frozen=True, platform="win32", env={"LOCALAPPDATA": r"C:\Users\h\AppData\Local"})
    assert win.name == "captionX" and "AppData" in str(win)
    assert paths.default_data_dir(frozen=True, platform="linux", env={"XDG_DATA_HOME": str(tmp_path)}) == tmp_path / "captionX"
    dev = paths.default_data_dir(frozen=False)
    assert dev.name == "data" and dev.parent.name == "backend"          # unchanged for `python run.py`
    assert isinstance(paths.frontend_dist(), Path)


def test_launcher_picks_a_free_port_and_recognises_itself():
    import socket
    import launcher
    with socket.socket() as s:                                          # occupy the preferred port
        try:
            s.bind(("127.0.0.1", launcher.PREFERRED_PORT))
        except OSError:
            pass
        p = launcher._pick_port()
        assert 1024 < p < 65536 and p != launcher.PREFERRED_PORT
    assert launcher._is_ours(1) is False


# ------------------------------------------------------------------------------ quit when the window closes
def test_presence_quits_only_after_the_window_is_really_gone():
    from app.presence import GRACE_SECONDS, STALE_SECONDS, Presence
    t = [1000.0]
    p = Presence(clock=lambda: t[0])
    assert p.should_quit() is False                       # never opened yet: don't quit
    p.ping("a"); p.ping("b")
    p.bye("a"); t[0] += GRACE_SECONDS + 1
    assert p.should_quit() is False                       # another tab is still open
    p.bye("b")
    t[0] += GRACE_SECONDS - 1
    assert p.should_quit() is False                       # inside the grace period (a reload)
    p.ping("c")                                           # the reloaded page comes back
    p.bye("c"); t[0] += GRACE_SECONDS + 0.5
    assert p.should_quit(busy=True) is False              # a job is running: stay alive
    t[0] += 1
    assert p.should_quit(busy=True) is False              # the countdown restarts after the job ends
    t[0] += GRACE_SECONDS + 1
    assert p.should_quit() is True
    p2 = Presence(clock=lambda: t[0]); p2.ping("x")       # page vanished without saying bye (sleep, crash)
    t[0] += STALE_SECONDS + 1
    assert p2.should_quit() is False
    t[0] += GRACE_SECONDS + 1
    assert p2.should_quit() is True


def test_presence_endpoints(client):
    from app.presence import presence
    assert client.post("/api/presence/ping", json={"id": "t1"}).json()["ok"] is True
    assert presence.count() >= 1
    # sendBeacon sends a Blob body with a JSON type
    assert client.post("/api/presence/bye", content=b'{"id": "t1"}', headers={"content-type": "application/json"}).status_code == 200
    assert client.post("/api/presence/bye", content=b"not json").status_code == 200   # never errors
