"""Settings model + on-disk store. Everything the Settings page edits lives here."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .paths import default_data_dir

DATA_DIR = Path(os.environ.get("CAPTIONS_DATA_DIR") or default_data_dir())
JOBS_DIR = DATA_DIR / "jobs"
SETTINGS_PATH = DATA_DIR / "settings.json"


class Settings(BaseModel):
    # --- Groq ---------------------------------------------------------------
    groq_api_key: str = ""

    # --- Speech-to-text (Whisper) -------------------------------------------
    stt_model: str = "whisper-large-v3"
    stt_language: str = "ur"  # "auto" = let Whisper detect
    stt_prompt: str = ""
    stt_temperature: float = Field(0.0, ge=0.0, le=1.0)

    # --- Romanization LLM ---------------------------------------------------
    llm_model: str = "openai/gpt-oss-120b"
    llm_temperature: float = Field(0.1, ge=0.0, le=1.0)
    llm_batch_size: int = Field(25, ge=1, le=80)
    llm_max_tokens: int = Field(8192, ge=256, le=32768)  # reasoning models spend tokens thinking
    system_prompt: str = ""  # empty => use built-in master prompt
    glossary: str = ""  # lines like:  فن => FANN
    casing: Literal["natural", "lowercase", "uppercase"] = "natural"
    strip_punctuation: bool = False

    # --- Caption shaping ----------------------------------------------------
    max_words_per_cue: int = Field(6, ge=1, le=25)
    max_cue_seconds: float = Field(3.5, ge=0.5, le=15.0)
    min_cue_seconds: float = Field(0.5, ge=0.1, le=5.0)
    gap_break_seconds: float = Field(0.7, ge=0.1, le=5.0)
    linger_ms: int = Field(150, ge=0, le=1500)
    max_chars_per_line: int = Field(32, ge=0, le=80)  # 0 = never wrap
    timing_offset_ms: int = Field(0, ge=-2000, le=2000)
    filter_hallucinations: bool = True

    # --- DaVinci Resolve FCPXML export --------------------------------------
    fcpxml_fps: Literal["23.976", "24", "25", "29.97", "30", "50", "59.94", "60"] = "30"
    fcpxml_resolution: str = Field("1080x1920", pattern=r"^\d{3,4}x\d{3,4}$")
    fcpxml_font: str = Field("Arial", min_length=1, max_length=80)
    fcpxml_font_face: str = Field("Bold", max_length=40)
    fcpxml_font_size: int = Field(72, ge=10, le=400)
    fcpxml_text_color: str = Field("#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    fcpxml_outline: bool = True
    fcpxml_outline_color: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    fcpxml_position_y: float = Field(0.70, ge=0.05, le=0.95)  # caption centre, as a fraction from the top

    # --- Audio / limits -----------------------------------------------------
    audio_format: Literal["flac", "mp3"] = "flac"
    chunk_seconds: int = Field(600, ge=60, le=1800)
    max_upload_mb: int = Field(500, ge=1, le=4000)
    max_duration_minutes: int = Field(60, ge=1, le=240)
    request_timeout_s: int = Field(120, ge=10, le=600)
    max_retries: int = Field(3, ge=0, le=8)


# Fields that may be overridden for a single run (Studio -> "Run options").
RUN_OVERRIDABLE = {
    "stt_model", "stt_language", "stt_prompt", "stt_temperature",
    "llm_model", "llm_temperature", "llm_batch_size", "system_prompt", "glossary",
    "casing", "strip_punctuation",
    "max_words_per_cue", "max_cue_seconds", "min_cue_seconds", "gap_break_seconds",
    "linger_ms", "max_chars_per_line", "timing_offset_ms", "filter_hallucinations",
}


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


class SettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._cache: Optional[Settings] = None

    # -- persistence ---------------------------------------------------------
    def _read(self) -> Settings:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                known = {k: v for k, v in raw.items() if k in Settings.model_fields}
                return Settings(**known)
            except (json.JSONDecodeError, ValidationError, OSError):
                # Corrupt file: keep a backup and fall back to defaults instead of crashing.
                try:
                    self.path.rename(self.path.with_suffix(".json.bak"))
                except OSError:
                    pass
        return Settings()

    def _write(self, s: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(s.model_dump_json(indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)  # the file holds an API key
        except OSError:
            pass
        os.replace(tmp, self.path)

    # -- public --------------------------------------------------------------
    def get(self) -> Settings:
        with self._lock:
            if self._cache is None:
                self._cache = self._read()
            return self._cache.model_copy()

    def effective_key(self, s: Optional[Settings] = None) -> tuple[str, Optional[str]]:
        s = s or self.get()
        if s.groq_api_key.strip():
            return s.groq_api_key.strip(), "settings"
        env = os.environ.get("GROQ_API_KEY", "").strip()
        if env:
            return env, "env"
        return "", None

    def update(self, patch: dict) -> Settings:
        with self._lock:
            current = self._cache or self._read()
            data = current.model_dump()
            for k, v in patch.items():
                if k in Settings.model_fields:
                    data[k] = v
            new = Settings(**data)  # raises ValidationError on bad values
            self._write(new)
            self._cache = new
            return new.model_copy()

    def reset(self, keep_key: bool = True) -> Settings:
        with self._lock:
            old = self._cache or self._read()
            new = Settings(groq_api_key=old.groq_api_key if keep_key else "")
            self._write(new)
            self._cache = new
            return new.model_copy()

    def public(self) -> dict:
        s = self.get()
        key, source = self.effective_key(s)
        d = s.model_dump()
        d.pop("groq_api_key")
        d["groq_api_key_set"] = bool(key)
        d["groq_api_key_masked"] = mask_key(key)
        d["groq_api_key_source"] = source
        return d


def merged_for_run(base: Settings, overrides: dict) -> Settings:
    """Settings for one job = saved settings + per-run overrides (validated)."""
    data = base.model_dump()
    for k, v in (overrides or {}).items():
        if k in RUN_OVERRIDABLE:
            data[k] = v
    return Settings(**data)


store = SettingsStore()
