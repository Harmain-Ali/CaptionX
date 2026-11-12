"""FastAPI app: settings, models, jobs, preview audio, exports."""
from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import __version__, audio, drt, fcpxml, fusion, paths, srt
from .config import DATA_DIR, JOBS_DIR, RUN_OVERRIDABLE, Settings, merged_for_run, store
from .errors import AppError
from .groq_client import call_with_retry, make_client
from .jobs import JobStore
from .pipeline import Pipeline
from .prompts import DEFAULT_SYSTEM_PROMPT
from .romanize import clean_roman
from .segmenter import align_roman_words

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("captions")

ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".webm", ".wma",
               ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mpeg", ".mpg", ".mpga", ".3gp"}

FALLBACK_STT = ["whisper-large-v3", "whisper-large-v3-turbo"]
FALLBACK_LLM = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
NOT_CHAT = ("whisper", "guard", "tts", "orpheus", "playai", "embed", "distil")

jobs = JobStore(JOBS_DIR)
pipeline = Pipeline(jobs, store, make_client)

@asynccontextmanager
async def lifespan(_: FastAPI):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jobs.mark_interrupted()
    if not audio.ffmpeg_path():
        log.warning("ffmpeg not found: install it or uploads will fail with FFMPEG_MISSING")
    yield


app = FastAPI(title="Roman Urdu Captions", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"], allow_headers=["*"],
)


# --------------------------------------------------------------------------- errors
@app.exception_handler(AppError)
async def _app_error(_: Request, e: AppError):
    return JSONResponse({"error": e.to_dict()}, status_code=e.status)


def _fields_from_validation(e: ValidationError) -> dict:
    return {".".join(str(p) for p in err["loc"]): err["msg"] for err in e.errors()}


@app.exception_handler(ValidationError)
async def _pyd_error(_: Request, e: ValidationError):
    return JSONResponse({"error": {"code": "INVALID_SETTINGS", "message": "Some values are out of range.",
                                   "hint": None, "fields": _fields_from_validation(e)}}, status_code=422)


@app.exception_handler(RequestValidationError)
async def _req_error(_: Request, e: RequestValidationError):
    return JSONResponse({"error": {"code": "INVALID_REQUEST", "message": "The request was not valid.",
                                   "hint": str(e.errors()[0].get("msg", "")) if e.errors() else None}},
                        status_code=422)


@app.exception_handler(Exception)
async def _unhandled(_: Request, e: Exception):
    log.exception("unhandled error")
    return JSONResponse({"error": {"code": "INTERNAL", "message": f"Unexpected error: {e}",
                                   "hint": "See the backend terminal for details."}}, status_code=500)


# --------------------------------------------------------------------------- health
@app.get("/api/health")
def health():
    s = store.get()
    key, source = store.effective_key(s)
    return {"ok": True, "version": __version__, **audio.tools_status(),
            "key_set": bool(key), "key_source": source, "data_dir": str(DATA_DIR)}


# --------------------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings():
    return store.public()


@app.put("/api/settings")
def put_settings(patch: dict):
    patch = dict(patch)
    for k in ("groq_api_key_set", "groq_api_key_masked", "groq_api_key_source"):
        patch.pop(k, None)
    if patch.pop("clear_api_key", False):
        patch["groq_api_key"] = ""
    elif "groq_api_key" in patch:
        key = str(patch["groq_api_key"]).strip()
        if not key or "…" in key or "•" in key:
            patch.pop("groq_api_key")  # never overwrite with an empty/masked value by accident
        else:
            patch["groq_api_key"] = key
    unknown = [k for k in patch if k not in Settings.model_fields]
    if unknown:
        raise AppError("INVALID_SETTINGS", f"Unknown setting(s): {', '.join(unknown)}", None, 422)
    store.update(patch)  # ValidationError handled globally
    return store.public()


@app.post("/api/settings/reset")
def reset_settings():
    store.reset(keep_key=True)
    return store.public()


@app.get("/api/settings/default-prompt")
def default_prompt():
    return {"prompt": DEFAULT_SYSTEM_PROMPT}


class KeyTest(BaseModel):
    api_key: Optional[str] = None


def _list_models(key: str, timeout: float):
    client = pipeline.client_factory(key, timeout)
    resp = call_with_retry(lambda: client.models.list(), retries=1, stage="settings")
    items = getattr(resp, "data", None) or []
    out = []
    for m in items:
        mid = getattr(m, "id", None) or (m.get("id") if isinstance(m, dict) else None)
        active = getattr(m, "active", True)
        if mid and active is not False:
            out.append(mid)
    return sorted(set(out))


@app.post("/api/settings/test-key")
def test_key(body: KeyTest):
    s = store.get()
    key = (body.api_key or "").strip()
    if not key or "…" in key or "•" in key:
        key, _ = store.effective_key(s)
    if not key:
        raise AppError("MISSING_API_KEY", "Paste an API key first.", None, 400, "settings")
    ids = _list_models(key, min(s.request_timeout_s, 30))
    return {"ok": True, "model_count": len(ids)}


@app.get("/api/models")
def models():
    s = store.get()
    key, _ = store.effective_key(s)
    fallback = {"stt": FALLBACK_STT, "llm": FALLBACK_LLM, "source": "fallback", "warning": None}
    if not key:
        fallback["warning"] = "Add an API key to load the live model list."
        return fallback
    try:
        ids = _list_models(key, min(s.request_timeout_s, 30))
    except AppError as e:
        fallback["warning"] = e.message
        return fallback
    stt = [m for m in ids if "whisper" in m]
    llm = [m for m in ids if not any(t in m for t in NOT_CHAT)]
    return {"stt": stt or FALLBACK_STT, "llm": llm or FALLBACK_LLM, "source": "live", "warning": None}


# --------------------------------------------------------------------------- jobs
def _snapshot(s: Settings) -> dict:
    return s.model_dump(exclude={"groq_api_key"})


def _parse_overrides(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        assert isinstance(data, dict)
    except (json.JSONDecodeError, AssertionError):
        raise AppError("INVALID_REQUEST", "Run options were not valid JSON.", None, 422)
    return {k: v for k, v in data.items() if k in RUN_OVERRIDABLE}


def _require_key() -> None:
    key, _ = store.effective_key()
    if not key:
        raise AppError("MISSING_API_KEY", "No Groq API key is set.",
                       "Open Settings and paste your key (free at console.groq.com/keys).", 400, "settings")


@app.post("/api/jobs", status_code=202)
async def create_job(file: UploadFile = File(...), overrides: str = Form("{}")):
    _require_key()
    ov = _parse_overrides(overrides)
    cfg = merged_for_run(store.get(), ov)  # validates ranges
    name = file.filename or "upload"
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise AppError("UNSUPPORTED_MEDIA", f"'{ext or name}' is not a supported audio/video type.",
                       "Use MP3, WAV, M4A, MP4, MOV, MKV, WEBM, FLAC or OGG.", 415)
    job_id = jobs.create(name, _snapshot(cfg), ov)
    dest = jobs.dir(job_id) / f"source{ext}"
    limit = cfg.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with dest.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise AppError("FILE_TOO_LARGE", f"The file is larger than {cfg.max_upload_mb} MB.",
                                   "Raise 'Max upload size' in Settings or export a smaller file.", 413)
                fh.write(chunk)
        if size == 0:
            raise AppError("EMPTY_FILE", "The uploaded file is empty (0 bytes).", None, 422)
    except Exception:
        jobs.delete(job_id)
        raise
    pipeline.submit(job_id, "full")
    return {"id": job_id}


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": jobs.list()}


@app.delete("/api/jobs")
def delete_all_jobs():
    return {"deleted": jobs.delete_all()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    meta = jobs.get(job_id)
    if meta["status"] == "done":
        meta["cues"] = [c.to_dict(public=True) for c in jobs.load_cues(job_id)]
    return meta


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    pipeline.cancel(job_id)
    jobs.delete(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    jobs.get(job_id)
    pipeline.cancel(job_id)
    return {"ok": True}


class Reprocess(BaseModel):
    overrides: dict = Field(default_factory=dict)


@app.post("/api/jobs/{job_id}/reprocess", status_code=202)
def reprocess(job_id: str, body: Reprocess):
    """Re-run segmentation + romanization from the saved Whisper transcript (no new STT call)."""
    meta = jobs.get(job_id)
    if meta["status"] in ("queued", "running"):
        raise AppError("JOB_BUSY", "This job is still running.", None, 409)
    if not meta.get("has_transcript"):
        raise AppError("NO_TRANSCRIPT", "This job has no saved transcript to re-process.",
                       "Upload the file again.", 409)
    _require_key()
    ov = {k: v for k, v in body.overrides.items() if k in RUN_OVERRIDABLE}
    cfg = Settings(**{**meta["config"], **ov})  # validates
    jobs.update(job_id, config=_snapshot(cfg), overrides={**meta.get("overrides", {}), **ov},
                warnings=[], casing=cfg.casing)
    pipeline.submit(job_id, "reprocess")
    return {"id": job_id}


class CueEdit(BaseModel):
    index: int
    roman: str = Field(max_length=600)


class CueEdits(BaseModel):
    edits: list[CueEdit]


@app.put("/api/jobs/{job_id}/cues")
def edit_cues(job_id: str, body: CueEdits):
    meta = jobs.get(job_id)
    if meta["status"] != "done":
        raise AppError("JOB_NOT_READY", "This job has no captions yet.", None, 409)
    cues = {c.index: c for c in jobs.load_cues(job_id)}
    s = Settings(**meta["config"])
    for ed in body.edits:
        c = cues.get(ed.index)
        if c is None:
            raise AppError("INVALID_REQUEST", f"There is no line #{ed.index}.", None, 422)
        c.roman = clean_roman(ed.roman, s)
        c.flags = [f for f in c.flags if f not in ("fallback", "check")]
        if "edited" not in c.flags:
            c.flags.append("edited")
        align_roman_words(c)
    ordered = [cues[i] for i in sorted(cues)]
    jobs.save_cues(job_id, ordered)
    return {"cues": [c.to_dict(public=True) for c in ordered]}


class ViewOptions(BaseModel):
    offset_ms: Optional[int] = Field(None, ge=-10000, le=10000)
    casing: Optional[Literal["natural", "lowercase", "uppercase"]] = None


@app.put("/api/jobs/{job_id}/options")
def set_options(job_id: str, body: ViewOptions):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    jobs.update(job_id, **fields)
    return {"ok": True, **fields}


@app.get("/api/jobs/{job_id}/audio")
def job_audio(job_id: str):
    jobs.get(job_id)
    p = jobs.dir(job_id) / "preview.mp3"
    if not p.exists():
        raise AppError("NO_PREVIEW", "The preview audio is not ready.", None, 404)
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "no-cache"})


@app.get("/api/jobs/{job_id}/export")
def export_job(job_id: str, format: Literal["srt", "vtt", "txt", "fcpxml", "fusion", "drt"] = "srt",
               script: Literal["roman", "urdu", "both"] = "roman",
               offset_ms: Optional[int] = None, casing: Optional[str] = None, download: bool = True,
               fps: Optional[str] = None, resolution: Optional[str] = None):
    meta = jobs.get(job_id)
    if meta["status"] != "done":
        raise AppError("JOB_NOT_READY", "This job has no captions yet.", None, 409)
    cues = jobs.load_cues(job_id)
    s = Settings(**meta["config"])
    off = meta.get("offset_ms", 0) if offset_ms is None else offset_ms
    cas = casing if casing in ("natural", "lowercase", "uppercase") else meta.get("casing", "natural")
    if format == "srt":
        body, mime = srt.to_srt(cues, off, cas, s.max_chars_per_line, script), "application/x-subrip"
    elif format == "vtt":
        body, mime = srt.to_vtt(cues, off, cas, s.max_chars_per_line, script), "text/vtt"
    elif format == "fcpxml":
        style = store.get()  # style/frame-rate defaults come from today's Settings, not the job snapshot
        body = fcpxml.to_fcpxml(cues, name=fcpxml.project_name(meta["filename"]), style=style,
                                fps=fps or style.fcpxml_fps, resolution=resolution or style.fcpxml_resolution,
                                offset_ms=off, casing=cas, max_chars=s.max_chars_per_line, script=script)
        mime = "application/xml"
    elif format == "fusion":
        style = store.get()
        body = fusion.to_fusion_setting(cues, style=style, fps=fps or style.fcpxml_fps,
                                        resolution=resolution or style.fcpxml_resolution, offset_ms=off,
                                        casing=cas, max_chars=s.max_chars_per_line, script=script)
        mime = "text/plain"
    elif format == "drt":
        style = store.get()
        blob = drt.to_drt(cues, style=style, fps=fps or style.fcpxml_fps,
                          resolution=resolution or style.fcpxml_resolution, offset_ms=off,
                          casing=cas, max_chars=s.max_chars_per_line, script=script)
        body, mime = "", "application/octet-stream"
    else:
        body, mime = srt.to_txt(cues, cas, script), "text/plain"
    stem = re.sub(r"[^\w\-. ]+", "_", Path(meta["filename"]).stem).strip() or "captions"
    suffix = {"roman": "roman-urdu", "urdu": "urdu", "both": "roman-urdu+urdu"}[script]
    headers = {}
    if download:
        fname = f"{stem}.{suffix}.{format}"
        if format == "fusion":
            fname = f"{stem}.textplus.setting"
        if format == "drt":
            fname = f"{stem}.textplus.drt"
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    if format == "drt":
        return Response(blob, media_type=mime, headers=headers)
    return Response(body.encode("utf-8"), media_type=f"{mime}; charset=utf-8", headers=headers)


# --------------------------------------------------------------------------- built frontend (optional)
DIST = paths.frontend_dist()


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except Exception:
            if path.startswith("api/") or path == "api":
                raise HTTPException(404, "Not found")  # unknown API routes must not answer with the web page
            return await super().get_response("index.html", scope)


if DIST.exists():
    app.mount("/", SPAFiles(directory=DIST, html=True), name="web")
