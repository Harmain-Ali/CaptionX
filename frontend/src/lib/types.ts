export interface Word { t: string; s: number; e: number; est: boolean }

export interface Cue {
  index: number;
  start: number;
  end: number;
  urdu: string;
  roman: string;
  words: Word[];
  flags: string[]; // fallback | check | edited
}

export interface JobError {
  code: string;
  message: string;
  hint?: string | null;
  stage?: string | null;
}

export type JobStatus = "queued" | "running" | "done" | "error" | "cancelled";
export type Stage = "queued" | "prepare" | "transcribe" | "segment" | "romanize" | "done";
export type Casing = "natural" | "lowercase" | "uppercase";

export interface RunConfig {
  stt_model: string;
  stt_language: string;
  stt_prompt: string;
  stt_temperature: number;
  llm_model: string;
  llm_temperature: number;
  llm_batch_size: number;
  system_prompt: string;
  glossary: string;
  casing: Casing;
  strip_punctuation: boolean;
  max_words_per_cue: number;
  max_cue_seconds: number;
  min_cue_seconds: number;
  gap_break_seconds: number;
  linger_ms: number;
  max_chars_per_line: number;
  timing_offset_ms: number;
  filter_hallucinations: boolean;
  [k: string]: unknown;
}

export interface JobStats {
  stt_seconds?: number;
  llm_seconds?: number;
  total_seconds?: number;
  chunks?: number;
  fallback_cues?: number;
  check_cues?: number;
}

export interface Job {
  id: string;
  filename: string;
  created_at: number;
  status: JobStatus;
  stage: Stage | string;
  progress: number;
  message: string;
  error: JobError | null;
  warnings: string[];
  duration: number | null;
  stats: JobStats;
  config: RunConfig;
  overrides: Record<string, unknown>;
  offset_ms: number;
  casing: Casing;
  has_transcript: boolean;
  has_preview: boolean;
  cue_count: number;
  cues?: Cue[];
}

export type JobSummary = Pick<Job, "id" | "filename" | "created_at" | "status" | "stage" | "progress" |
  "duration" | "cue_count" | "error" | "stats" | "config">;

export interface SettingsPublic extends RunConfig {
  audio_format: "flac" | "mp3";
  chunk_seconds: number;
  max_upload_mb: number;
  max_duration_minutes: number;
  request_timeout_s: number;
  max_retries: number;
  llm_max_tokens: number;
  fcpxml_fps: string;
  fcpxml_resolution: string;
  fcpxml_font: string;
  fcpxml_font_face: string;
  fcpxml_font_size: number;
  fcpxml_text_color: string;
  fcpxml_outline: boolean;
  fcpxml_outline_color: string;
  fcpxml_position_y: number;
  groq_api_key_set: boolean;
  groq_api_key_masked: string;
  groq_api_key_source: "settings" | "env" | null;
}

export interface Health {
  ok: boolean;
  version: string;
  ffmpeg: boolean;
  ffprobe: boolean;
  key_set: boolean;
  key_source: string | null;
  data_dir: string;
}

export interface ModelList { stt: string[]; llm: string[]; source: "live" | "fallback"; warning: string | null }
