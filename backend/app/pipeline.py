"""Runs one job end to end in a background thread and reports progress."""
from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from . import audio
from .config import Settings, SettingsStore
from .errors import AppError, Cancelled
from .groq_client import make_client
from .jobs import JobStore
from .romanize import Romanizer
from .segmenter import Cue, build_cues
from .transcribe import Seg, filter_hallucinations, transcribe_chunk

log = logging.getLogger("captions")

SILENT_DB = -55.0  # louder than this = something is on the track


class Pipeline:
    def __init__(self, jobs: JobStore, store: SettingsStore, client_factory: Callable = make_client):
        self.jobs, self.store, self.client_factory = jobs, store, client_factory
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
        self._cancel: dict[str, threading.Event] = {}

    # -- public --------------------------------------------------------------
    def submit(self, job_id: str, mode: str = "full") -> None:
        self._cancel[job_id] = threading.Event()
        self.jobs.update(job_id, status="queued", stage="queued", progress=0.0, error=None,
                         message="Queued")
        self.pool.submit(self._run, job_id, mode)

    def cancel(self, job_id: str) -> None:
        ev = self._cancel.get(job_id)
        if ev:
            ev.set()

    # -- helpers -------------------------------------------------------------
    def _set(self, job_id: str, stage: str, progress: float, message: str) -> None:
        self.jobs.update(job_id, status="running", stage=stage, progress=round(progress, 3), message=message)

    # -- the job -------------------------------------------------------------
    def _run(self, job_id: str, mode: str) -> None:
        t0 = time.time()
        stage = "prepare"
        cancel_ev = self._cancel.setdefault(job_id, threading.Event())

        def check_cancel():
            if cancel_ev.is_set():
                raise Cancelled()

        def note(msg: str):
            self.jobs.update(job_id, message=msg)

        try:
            meta = self.jobs.get(job_id)
            s = Settings(**meta["config"])
            key, _ = self.store.effective_key()
            if not key:
                raise AppError("MISSING_API_KEY", "No Groq API key is set.",
                               "Open Settings and paste your key (free at console.groq.com/keys).", 400, "prepare")
            client = self.client_factory(key, s.request_timeout_s)
            jd = self.jobs.dir(job_id)
            warnings: list[str] = []
            stats = dict(meta.get("stats") or {})

            # ---------------------------------------------------------------- full run: audio + Whisper
            if mode == "full":
                stage = "prepare"
                self._set(job_id, stage, 0.02, "Checking the file…")
                audio.require_tools()
                src = next(jd.glob("source.*"))
                info = audio.probe(src)
                if not info.has_audio:
                    raise AppError("NO_AUDIO_STREAM", "This file has no audio track.",
                                   "Export it with the audio included (or upload the audio file).", 422, stage)
                if info.duration and info.duration < 0.3:
                    raise AppError("TOO_SHORT", "The file is shorter than a third of a second.", None, 422, stage)
                if info.duration > s.max_duration_minutes * 60:
                    raise AppError("TOO_LONG", f"The file is {info.duration/60:.0f} min long; your limit is "
                                   f"{s.max_duration_minutes} min.",
                                   "Raise 'Max duration' in Settings or trim the file.", 422, stage)
                self.jobs.update(job_id, duration=round(info.duration, 2))
                check_cancel()

                self._set(job_id, stage, 0.05, "Converting audio for Whisper…")
                chunks = audio.prepare_stt_audio(src, jd, s.audio_format, s.chunk_seconds, check_cancel)
                loud = audio.max_volume_db(chunks[0].path) if len(chunks) == 1 else None
                if loud is not None and loud < SILENT_DB:
                    raise AppError("NO_SPEECH", "The audio track is silent.",
                                   "Check that you exported the right track (not a muted one).", 422, stage)
                self._set(job_id, stage, 0.09, "Building the preview audio…")
                audio.make_preview(src, jd / "preview.mp3")
                self.jobs.update(job_id, has_preview=True)

                stage = "transcribe"
                all_segs: list[Seg] = []
                t_stt = time.time()
                for i, ch in enumerate(chunks):
                    check_cancel()
                    self._set(job_id, stage, 0.10 + 0.45 * (i / len(chunks)),
                              f"Transcribing with Whisper ({i + 1}/{len(chunks)})…")
                    all_segs.extend(transcribe_chunk(client, ch, s, check_cancel, note))
                stats["stt_seconds"] = round(time.time() - t_stt, 1)
                stats["chunks"] = len(chunks)
                self.jobs.save_transcript(job_id, [sg.to_dict() for sg in all_segs])
                self.jobs.update(job_id, has_transcript=True)
            else:
                raw = self.jobs.load_transcript(job_id)
                if raw is None:
                    raise AppError("NO_TRANSCRIPT", "There is no saved transcript for this job.",
                                   "Upload the file again.", 409, stage)
                all_segs = [Seg.from_dict(d) for d in raw]
                for sg in all_segs:
                    sg.dropped = None

            # ---------------------------------------------------------------- shape cues
            stage = "segment"
            self._set(job_id, stage, 0.57, "Shaping caption lines…")
            check_cancel()
            if s.filter_hallucinations:
                segs, dropped = filter_hallucinations(all_segs)
                if dropped:
                    warnings.append(f"{dropped} segment(s) were removed as probable Whisper hallucinations "
                                    "(text over silence or repeated loops).")
            else:
                segs = [sg for sg in all_segs if sg.text.strip()]
            if not segs:
                raise AppError("NO_SPEECH", "Whisper did not find any speech in this file.",
                               "Check the language setting (Urdu = 'ur'), the audio level, or try the "
                               "whisper-large-v3 model.", 422, stage)
            cues = build_cues(segs, s)
            if not cues:
                raise AppError("NO_SPEECH", "No usable caption lines were produced.", None, 422, stage)

            # ---------------------------------------------------------------- romanize
            stage = "romanize"
            t_llm = time.time()

            def prog(done: int, total: int):
                self._set(job_id, stage, 0.60 + 0.37 * (done / max(total, 1)),
                          f"Romanizing with {s.llm_model} ({min(done + 1, total)}/{total})…")

            Romanizer(client, s, check_cancel, note).run(cues, prog)
            stats["llm_seconds"] = round(time.time() - t_llm, 1)

            n_fb = sum("fallback" in c.flags for c in cues)
            n_chk = sum("check" in c.flags for c in cues)
            if n_fb:
                warnings.append(f"{n_fb} line(s) used the rough offline fallback because the model failed. "
                                "They are marked in amber, please review them.")
            if n_chk:
                warnings.append(f"{n_chk} line(s) look suspicious (length differs a lot from the source). "
                                "They are marked 'check'.")
            stats.update(total_seconds=round(time.time() - t0, 1), fallback_cues=n_fb, check_cues=n_chk)

            self.jobs.save_cues(job_id, cues)
            self.jobs.update(job_id, status="done", stage="done", progress=1.0, message="Done",
                             cue_count=len(cues), warnings=warnings, stats=stats, error=None)

        except Cancelled:
            self.jobs.update(job_id, status="cancelled", message="Cancelled", error=None)
        except AppError as e:
            e.stage = e.stage or stage
            self.jobs.update(job_id, status="error", stage=e.stage, message=e.message, error=e.to_dict())
        except Exception as e:  # never leave a job stuck in "running"
            log.error("job %s crashed:\n%s", job_id, traceback.format_exc())
            self.jobs.update(job_id, status="error", stage=stage, message=str(e), error={
                "code": "INTERNAL", "message": f"Unexpected error: {e}",
                "hint": "See the backend terminal for the full traceback.", "stage": stage})
        finally:
            self._cancel.pop(job_id, None)
