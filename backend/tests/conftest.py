import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

# Isolated data dir + no real key, BEFORE the app is imported.
_TMP = tempfile.mkdtemp(prefix="captions-test-")
os.environ["CAPTIONS_DATA_DIR"] = _TMP
os.environ.pop("GROQ_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import groq  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.config import store  # noqa: E402
from app.romanize import fallback_romanize  # noqa: E402


def groq_error(cls, status, message="boom", headers=None):
    req = httpx.Request("POST", "https://api.groq.com/x")
    resp = httpx.Response(status, request=req, headers=headers or {})
    return cls(message, response=resp, body={"error": {"message": message}})


class FakeGroq:
    """Mimics the parts of the Groq SDK the app uses. Behaviours are swapped per test."""

    def __init__(self):
        self.stt_calls = 0
        self.llm_calls = 0
        self.stt_response = None          # callable or None -> default
        self.llm_behavior = "ok"          # ok | garbage | missing | urdu | auth | ratelimit_once
        self._rl_done = False
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._stt))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._llm))
        self.models = SimpleNamespace(list=self._models)

    def _models(self):
        return SimpleNamespace(data=[SimpleNamespace(id=i, active=True) for i in
                                     ["whisper-large-v3", "whisper-large-v3-turbo", "llama-3.3-70b-versatile",
                                      "llama-3.1-8b-instant", "meta-llama/llama-guard-4-12b"]])

    def _stt(self, **kw):
        self.stt_calls += 1
        if self.stt_response:
            return self.stt_response(kw)
        # segments/words as plain dicts, like the real SDK's extra fields
        return SimpleNamespace(
            text="x",
            segments=[
                {"text": "السلام علیکم دوستو آج ہم بات کریں گے", "start": 0.2, "end": 2.6,
                 "no_speech_prob": 0.01, "avg_logprob": -0.2, "compression_ratio": 1.2},
                {"text": "یہ بہت آسان ہے آپ بھی کر سکتے ہیں۔", "start": 3.0, "end": 5.5,
                 "no_speech_prob": 0.01, "avg_logprob": -0.2, "compression_ratio": 1.2},
            ],
            words=[{"word": w, "start": 0.2 + i * 0.3, "end": 0.45 + i * 0.3}
                   for i, w in enumerate("السلام علیکم دوستو آج ہم بات کریں گے".split())]
            + [{"word": w, "start": 3.0 + i * 0.3, "end": 3.25 + i * 0.3}
               for i, w in enumerate("یہ بہت آسان ہے آپ بھی کر سکتے ہیں۔".split())],
        )

    def _llm(self, **kw):
        self.llm_calls += 1
        b = self.llm_behavior
        if b == "auth":
            raise groq_error(groq.AuthenticationError, 401, "Invalid API Key")
        if b == "jsonmode_fail" and "response_format" in kw:
            raise groq_error(groq.BadRequestError, 400,
                             "Failed to validate JSON. Please adjust your prompt. See 'failed_generation' for more details.")
        if b == "ratelimit_once" and not self._rl_done:
            self._rl_done = True
            raise groq_error(groq.RateLimitError, 429, "slow down", {"retry-after": "0"})
        payload = json.loads(kw["messages"][-1]["content"])
        cues = payload["cues"]
        if b == "garbage":
            content = "Sure! here you go: not json"
        elif b == "missing":
            # drops the last id whenever there is more than one cue
            keep = cues[:-1] if len(cues) > 1 else cues
            content = json.dumps({"cues": [{"id": c["id"], "roman": fallback_romanize(c["text"])} for c in keep]})
        elif b == "fewer":  # glues the first two words together => word counts no longer match
            content = json.dumps({"cues": [{"id": c["id"], "roman": fallback_romanize(c["text"]).replace(" ", "", 1)} for c in cues]})
        elif b == "urdu":
            content = json.dumps({"cues": [{"id": c["id"], "roman": c["text"]} for c in cues]})
        else:
            content = json.dumps({"cues": [{"id": c["id"], "roman": fallback_romanize(c["text"])} for c in cues]})
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content), finish_reason="stop")])


@pytest.fixture()
def fake(monkeypatch):
    f = FakeGroq()
    monkeypatch.setattr(main.pipeline, "client_factory", lambda key, timeout: f)
    store.reset(keep_key=False)
    store.update({"groq_api_key": "gsk_test_key_123456", "max_retries": 2})
    return f


@pytest.fixture()
def client():
    with TestClient(main.app) as c:
        yield c


def make_media(path: Path, kind: str = "tone", seconds: float = 6.0) -> Path:
    if kind == "tone":
        args = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    elif kind == "silence":
        args = ["-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono", "-t", str(seconds)]
    elif kind == "video_no_audio":
        args = ["-f", "lavfi", "-i", f"color=c=black:s=64x64:d={seconds}", "-pix_fmt", "yuv420p"]
    else:
        raise ValueError(kind)
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args, str(path)], check=True)
    return path


def wait_job(client, job_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError("job did not finish: " + json.dumps(j))


def upload(client, path: Path, overrides=None):
    with path.open("rb") as fh:
        return client.post("/api/jobs", files={"file": (path.name, fh)},
                           data={"overrides": json.dumps(overrides or {})})
