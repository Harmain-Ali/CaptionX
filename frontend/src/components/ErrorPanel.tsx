import type { ReactNode } from "react";
import { Icon } from "./Icon";

const TITLES: Record<string, string> = {
  BACKEND_OFFLINE: "Backend not running",
  MISSING_API_KEY: "Groq API key needed",
  INVALID_API_KEY: "Groq rejected the API key",
  RATE_LIMITED: "Groq rate limit reached",
  NETWORK_ERROR: "No connection to Groq",
  TIMEOUT: "Groq timed out",
  MODEL_NOT_FOUND: "Model unavailable",
  UNSUPPORTED_MEDIA: "Can't read this file",
  MEDIA_DECODE_FAILED: "Can't decode the audio",
  NO_AUDIO_STREAM: "No audio in this file",
  NO_SPEECH: "No speech found",
  TOO_LONG: "File is too long",
  TOO_SHORT: "File is too short",
  FILE_TOO_LARGE: "File is too large",
  EMPTY_FILE: "Empty file",
  FFMPEG_MISSING: "ffmpeg is not installed",
  PAYLOAD_TOO_LARGE: "Audio chunk too large for Groq",
  INVALID_SETTINGS: "Some settings are invalid",
  INTERRUPTED: "Job was interrupted",
  JOB_NOT_FOUND: "Job not found",
};

export const SETTINGS_CODES = new Set(["MISSING_API_KEY", "INVALID_API_KEY", "MODEL_NOT_FOUND", "PERMISSION_DENIED"]);

export function ErrorPanel({ code, message, hint, stage, children }: {
  code: string; message: string; hint?: string | null; stage?: string | null; children?: ReactNode;
}) {
  return (
    <div className="error-panel" role="alert">
      <div className="error-icon"><Icon name="alert" size={22} /></div>
      <div className="error-body">
        <h3>{TITLES[code] ?? "Something went wrong"}</h3>
        <p>{message}</p>
        {hint && <p className="hint">{hint}</p>}
        <div className="error-meta">
          <code>{code}</code>{stage && <span>during <b>{stage}</b></span>}
        </div>
        {children && <div className="error-actions">{children}</div>}
      </div>
    </div>
  );
}
