"""Tiny file-based job store: every job is a folder under data/jobs/<id>/ (survives restarts)."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .config import JOBS_DIR
from .errors import AppError
from .segmenter import Cue


class JobStore:
    def __init__(self, base: Path = JOBS_DIR):
        self.base = base
        self.lock = threading.RLock()

    # -- paths ---------------------------------------------------------------
    def dir(self, job_id: str) -> Path:
        if not job_id.isalnum():  # ids are hex: blocks path traversal like ../../x
            raise AppError("JOB_NOT_FOUND", "Job not found.", None, 404)
        return self.base / job_id

    def _meta_path(self, job_id: str) -> Path:
        return self.dir(job_id) / "job.json"

    # -- meta ----------------------------------------------------------------
    def create(self, filename: str, config: dict, overrides: dict) -> str:
        job_id = uuid.uuid4().hex[:12]
        d = self.dir(job_id)
        d.mkdir(parents=True, exist_ok=True)
        meta = {
            "id": job_id, "filename": filename, "created_at": time.time(),
            "status": "queued", "stage": "queued", "progress": 0.0, "message": "Queued",
            "error": None, "warnings": [], "duration": None, "stats": {},
            "config": config, "overrides": overrides,
            "offset_ms": config.get("timing_offset_ms", 0), "casing": config.get("casing", "natural"),
            "has_transcript": False, "has_preview": False, "cue_count": 0,
        }
        self._write_json(self._meta_path(job_id), meta)
        return job_id

    def get(self, job_id: str) -> dict:
        p = self._meta_path(job_id)
        if not p.exists():
            raise AppError("JOB_NOT_FOUND", "That job no longer exists.", None, 404)
        with self.lock:
            return json.loads(p.read_text(encoding="utf-8"))

    def update(self, job_id: str, **fields: Any) -> dict:
        with self.lock:
            meta = self.get(job_id)
            meta.update(fields)
            self._write_json(self._meta_path(job_id), meta)
            return meta

    def list(self) -> list[dict]:
        out = []
        if self.base.exists():
            for d in self.base.iterdir():
                p = d / "job.json"
                if p.exists():
                    try:
                        m = json.loads(p.read_text(encoding="utf-8"))
                        out.append({k: m.get(k) for k in (
                            "id", "filename", "created_at", "status", "stage", "progress", "duration",
                            "cue_count", "error", "stats", "config")})
                    except (json.JSONDecodeError, OSError):
                        continue
        out.sort(key=lambda m: m.get("created_at") or 0, reverse=True)
        return out

    def delete(self, job_id: str) -> None:
        d = self.dir(job_id)
        if not d.exists():
            raise AppError("JOB_NOT_FOUND", "That job no longer exists.", None, 404)
        shutil.rmtree(d, ignore_errors=True)

    def delete_all(self) -> int:
        n = 0
        if self.base.exists():
            for d in list(self.base.iterdir()):
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)
                    n += 1
        return n

    def mark_interrupted(self) -> None:
        for m in self.list():
            if m["status"] in ("queued", "running"):
                self.update(m["id"], status="error", stage=m.get("stage"), error={
                    "code": "INTERRUPTED", "message": "The app was closed while this job was running.",
                    "hint": "Upload the file again.", "stage": m.get("stage")})

    # -- cues / transcript ---------------------------------------------------
    def save_cues(self, job_id: str, cues: list[Cue]) -> None:
        self._write_json(self.dir(job_id) / "cues.json", [c.to_dict() for c in cues])

    def load_cues(self, job_id: str) -> list[Cue]:
        p = self.dir(job_id) / "cues.json"
        if not p.exists():
            return []
        return [Cue.from_dict(d) for d in json.loads(p.read_text(encoding="utf-8"))]

    def save_transcript(self, job_id: str, segs: list[dict]) -> None:
        self._write_json(self.dir(job_id) / "transcript.json", segs)

    def load_transcript(self, job_id: str) -> Optional[list[dict]]:
        p = self.dir(job_id) / "transcript.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    # -- io ------------------------------------------------------------------
    def _write_json(self, path: Path, data: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
