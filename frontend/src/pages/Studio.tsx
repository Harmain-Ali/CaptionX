import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useJob } from "../lib/useJob";
import { useHealth } from "../lib/health";
import { go, href } from "../lib/router";
import { ago } from "../lib/format";
import { REUSE_KEY } from "../lib/links";
import { Info } from "../components/Info";
import type { JobSummary, ModelList, SettingsPublic } from "../lib/types";
import { ErrorPanel, SETTINGS_CODES } from "../components/ErrorPanel";
import { ProgressCard } from "../components/ProgressCard";
import { ResultView } from "../components/ResultView";
import { RunOptions, optionsValid } from "../components/RunOptions";
import { UploadCard } from "../components/UploadCard";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";

const RUN_KEYS = ["stt_model", "stt_language", "stt_prompt", "stt_temperature", "llm_model", "llm_temperature", "llm_batch_size",
  "system_prompt", "glossary", "casing", "strip_punctuation", "max_words_per_cue", "max_cue_seconds", "min_cue_seconds",
  "gap_break_seconds", "linger_ms", "max_chars_per_line", "timing_offset_ms", "filter_hallucinations"];

/* ------------------------------------------------------------------------------- new upload */
function NewJob() {
  const { health, offline } = useHealth();
  const toast = useToast();
  const [settings, setSettings] = useState<SettingsPublic | null>(null);
  const [models, setModels] = useState<ModelList | null>(null);
  const [recent, setRecent] = useState<JobSummary[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [reuse, setReuse] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {  // "Use these settings" from History
    if (!settings) return;
    try {
      const raw = sessionStorage.getItem(REUSE_KEY);
      if (!raw) return;
      sessionStorage.removeItem(REUSE_KEY);
      const { name, config } = JSON.parse(raw) as { name: string; config: Record<string, unknown> };
      const base = settings as unknown as Record<string, unknown>;
      const diff: Record<string, unknown> = {};
      for (const k of RUN_KEYS) if (k in config && JSON.stringify(config[k]) !== JSON.stringify(base[k])) diff[k] = config[k];
      setOverrides(diff);
      setReuse(name);
    } catch { /* ignore a bad value */ }
  }, [settings]);

  useEffect(() => {
    if (offline) return;
    api.settings().then(setSettings).catch(() => {});
    api.models().then(setModels).catch(() => {});
    api.jobs().then((r) => setRecent(r.jobs.slice(0, 4))).catch(() => {});
  }, [offline, health?.key_set]);

  const uploading = progress !== null;
  const keyMissing = !!health && !health.key_set;
  const ffmpegMissing = !!health && !(health.ffmpeg && health.ffprobe);
  const valid = settings ? optionsValid(settings, overrides) : false;
  const blocked = offline || keyMissing || ffmpegMissing || !settings;

  const start = async () => {
    if (!file) return;
    setError(null);
    setProgress(0);
    abort.current = new AbortController();
    try {
      const { id } = await api.upload(file, overrides, setProgress, abort.current.signal);
      go(href.job(id));
    } catch (e) {
      const err = e as ApiError;
      if (err.code !== "ABORTED") setError(err);
      else toast("Upload cancelled", "info");
      setProgress(null);
    }
  };

  return (
    <div className="narrow">
      <div className="intro">
        <div className="row"><h1>Turn speech into Roman Urdu captions</h1></div>
        <p>Drop in a reel or voice-over. Check the timing line by line, then export for DaVinci Resolve, CapCut or anywhere else.</p>
      </div>

      {offline && <ErrorPanel code="BACKEND_OFFLINE" message="The caption server isn't responding."
        hint="Start it with run.sh (macOS/Linux) or run.bat (Windows), then this page reconnects by itself." />}
      {!offline && ffmpegMissing && <ErrorPanel code="FFMPEG_MISSING" message="ffmpeg wasn't found on this computer, so audio can't be prepared."
        hint="Install it (Windows: winget install Gyan.FFmpeg, macOS: brew install ffmpeg, Linux: sudo apt install ffmpeg) and restart the backend." />}
      {!offline && keyMissing && (
        <ErrorPanel code="MISSING_API_KEY" message="Add your free Groq API key to start."
          hint="Get one at console.groq.com/keys. No credit card needed.">
          <a className="btn primary sm" href={href.settings}><Icon name="key" size={15} /> Open settings</a>
        </ErrorPanel>
      )}

      <UploadCard file={file} onFile={(f) => { setFile(f); setError(null); }} disabled={uploading}
                  maxMb={settings?.max_upload_mb ?? 500} progress={uploading ? progress : null} />

      {error && (
        <ErrorPanel code={error.code} message={error.message} hint={error.hint} stage={error.stage}>
          {SETTINGS_CODES.has(error.code) || error.code === "FILE_TOO_LARGE"
            ? <a className="btn sm" href={href.settings}>Open settings</a> : null}
        </ErrorPanel>
      )}

      {reuse && <p className="reuse-note"><Icon name="check" size={15} /> Using the settings from “{reuse}”. Change anything below, or reset to go back to your saved settings.</p>}
      {settings && <RunOptions key={reuse ?? "saved"} defaultOpen={!!reuse} base={settings} value={overrides} onChange={setOverrides} models={models} />}

      <div className="actions">
        {uploading ? (
          <button className="btn" onClick={() => abort.current?.abort()}>Cancel upload</button>
        ) : (
          <button className="btn primary lg" disabled={!file || blocked || !valid} onClick={start}>
            Generate captions
          </button>
        )}
        {uploading && <span className="muted">{progress! < 1 ? `Uploading ${Math.round(progress! * 100)}%` : "Starting…"}</span>}
        {!uploading && file && blocked && !offline && <span className="muted">Fix the message above first.</span>}
      </div>

      {recent.length > 0 && (
        <section className="recent">
          <div className="recent-head"><div className="row"><h2>Recent</h2><Info>Your last few files. Open the History page to see all of them and the settings each one used.</Info></div><a href={href.history}>See all</a></div>
          <ul>
            {recent.map((j) => (
              <li key={j.id}>
                <a href={href.job(j.id)}>
                  <b>{j.filename}</b>
                  <span className={`tag ${j.status}`}>{j.status === "done" ? `${j.cue_count} lines` : j.status}</span>
                  <span className="muted">{ago(j.created_at)}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------------- job page */
function JobPage({ id }: { id: string }) {
  const { job, error, reload } = useJob(id);
  const [models, setModels] = useState<ModelList | null>(null);
  const toast = useToast();
  useEffect(() => { api.models().then(setModels).catch(() => {}); }, []);

  const retry = async () => {
    try {
      const cur = await api.settings(); // retry with today's settings, e.g. a model you just switched
      await api.reprocess(id, cur);
      await reload();
    }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const cancel = async () => { try { await api.cancel(id); } catch { /* already finished */ } await reload(); };

  if (!job) {
    if (error) {
      return (
        <div className="narrow">
          <ErrorPanel code={error.code} message={error.message} hint={error.hint}>
            <a className="btn sm" href={href.studio}>New captions</a>
          </ErrorPanel>
        </div>
      );
    }
    return <div className="narrow"><div className="skeleton" aria-busy="true" aria-label="Loading" /></div>;
  }

  if (job.status === "queued" || job.status === "running") {
    return (
      <div className="narrow">
        <ProgressCard job={job} onCancel={cancel} />
        {error?.code === "BACKEND_OFFLINE" && <ErrorPanel code={error.code} message={error.message} hint={error.hint} />}
      </div>
    );
  }

  if (job.status === "cancelled") {
    return (
      <div className="narrow">
        <section className="card empty">
          <h2>Cancelled</h2>
          <p className="muted">Nothing was saved for this run.</p>
          <a className="btn primary" href={href.studio}>Start again</a>
        </section>
      </div>
    );
  }

  if (job.status === "error" && job.error) {
    const canRetry = job.has_transcript;
    return (
      <div className="narrow">
        <ErrorPanel code={job.error.code} message={job.error.message} hint={job.error.hint} stage={job.error.stage}>
          {SETTINGS_CODES.has(job.error.code) && <a className="btn sm" href={href.settings}><Icon name="settings" size={15} /> Open settings</a>}
          {canRetry && <button className="btn primary sm" onClick={retry}><Icon name="refresh" size={15} /> Retry without re-transcribing</button>}
          <a className="btn ghost sm" href={href.studio}>Try another file</a>
        </ErrorPanel>
        {canRetry && <p className="muted sm">Your Whisper transcript is saved, so retrying only repeats the Roman Urdu step.</p>}
      </div>
    );
  }

  return <ResultView job={job} models={models} reload={reload} />;
}

export function Studio({ jobId }: { jobId?: string }) {
  return jobId ? <JobPage key={jobId} id={jobId} /> : <NewJob />;
}
