import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import { api, ApiError } from "../lib/api";
import { ago, clock } from "../lib/format";
import { go, href } from "../lib/router";
import { REUSE_KEY } from "../lib/links";
import { itemVariants, listVariants } from "../lib/motion";
import type { JobSummary } from "../lib/types";
import { Disclosure } from "../components/Disclosure";
import { ErrorPanel } from "../components/ErrorPanel";
import { Icon } from "../components/Icon";
import { Info } from "../components/Info";
import { useToast } from "../components/Toast";

const LABELS: [string, string, (v: unknown) => string][] = [
  ["stt_model", "Speech model", String],
  ["stt_language", "Language", String],
  ["llm_model", "Romanization model", String],
  ["casing", "Letter case", String],
  ["max_words_per_cue", "Words per line", String],
  ["max_cue_seconds", "Max seconds per line", (v) => `${v} s`],
  ["min_cue_seconds", "Min seconds per line", (v) => `${v} s`],
  ["gap_break_seconds", "Pause that splits a line", (v) => `${v} s`],
  ["linger_ms", "Linger", (v) => `${v} ms`],
  ["max_chars_per_line", "Wrap width", (v) => (Number(v) === 0 ? "never" : `${v} characters`)],
  ["timing_offset_ms", "Default timing offset", (v) => `${v} ms`],
  ["stt_temperature", "Speech temperature", String],
  ["llm_temperature", "Romanization temperature", String],
  ["llm_batch_size", "Lines per request", String],
  ["strip_punctuation", "Strip punctuation", (v) => (v ? "yes" : "no")],
  ["filter_hallucinations", "Hallucination filter", (v) => (v ? "on" : "off")],
  ["stt_prompt", "Vocabulary hint", (v) => (String(v).trim() ? String(v).trim().slice(0, 60) : "none")],
  ["glossary", "Glossary rules", (v) => String(String(v).split("\n").filter((l) => l.trim()).length)],
  ["system_prompt", "Master prompt", (v) => (String(v).trim() ? "custom" : "built-in")],
];

function SettingsUsed({ j }: { j: JobSummary }) {
  const cfg = (j.config ?? {}) as Record<string, unknown>;
  const reuse = () => {
    try { sessionStorage.setItem(REUSE_KEY, JSON.stringify({ name: j.filename, config: cfg })); } catch { /* private mode */ }
    go(href.studio);
  };
  return (
    <div className="used">
      <dl className="kv">
        {LABELS.filter(([k]) => k in cfg).map(([k, label, fmt]) => (
          <div key={k}><dt>{label}</dt><dd title={String(cfg[k])}>{fmt(cfg[k])}</dd></div>
        ))}
      </dl>
      <button className="btn sm" onClick={reuse}><Icon name="refresh" size={15} /> Use these settings for a new file</button>
    </div>
  );
}

export function History() {
  const toast = useToast();
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    try { setJobs((await api.jobs()).jobs); setError(null); } catch (e) { setError(e as ApiError); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const del = async (j: JobSummary) => {
    if (!window.confirm(`Delete “${j.filename}” and its audio from this computer?`)) return;
    try { await api.deleteJob(j.id); setJobs((xs) => xs?.filter((x) => x.id !== j.id) ?? null); toast("Deleted"); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const delAll = async () => {
    if (!window.confirm("Delete ALL past jobs and their audio from this computer?")) return;
    try { const r = await api.deleteAllJobs(); toast(`Deleted ${r.deleted} job${r.deleted === 1 ? "" : "s"}`); setJobs([]); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  return (
    <div className="narrow wide">
      <div className="page-head">
        <div className="row"><h1>History</h1><Info>Every file you've captioned, kept on this computer only. Open one to keep editing, or expand “Settings used” to see exactly how it was made and reuse those settings.</Info></div>
        <div className="row">
          <button className="btn sm" onClick={load}><Icon name="refresh" size={15} /> Refresh</button>
          {jobs && jobs.length > 0 && <button className="btn sm danger-text" onClick={delAll}>Delete all</button>}
        </div>
      </div>
      {error && <ErrorPanel code={error.code} message={error.message} hint={error.hint} />}
      {jobs && jobs.length === 0 && (
        <section className="card empty">
          <div className="empty-mark"><Icon name="history" size={26} /></div>
          <h2>No captions yet</h2>
          <p className="muted">Everything you generate shows up here, with the settings it used.</p>
          <a className="btn primary" href={href.studio}>Make your first captions</a>
        </section>
      )}
      {jobs && jobs.length > 0 && (
        <motion.ul className="history" variants={listVariants} initial="initial" animate="animate">
          {jobs.map((j) => (
            <motion.li key={j.id} className="card hist" variants={itemVariants} layout="position">
              <div className="hist-row">
                <a className="history-main" href={href.job(j.id)}>
                  <b title={j.filename}>{j.filename}</b>
                  <span className="muted sm">{ago(j.created_at)}{j.duration ? ` · ${clock(j.duration)}` : ""}{j.status === "done" ? ` · ${j.cue_count} lines` : ""}</span>
                </a>
                <span className={`tag ${j.status}`}>{j.status}</span>
                <button className="icon-btn" aria-label={`Delete ${j.filename}`} onClick={() => del(j)}><Icon name="trash" size={17} /></button>
              </div>
              {j.status === "error" && j.error && <p className="hist-error"><Icon name="alert" size={14} /> {j.error.message}</p>}
              <Disclosure className="hist-used" head={<span className="sm">Settings used <span className="muted">· {String(j.config?.llm_model ?? "")}</span></span>}>
                <SettingsUsed j={j} />
              </Disclosure>
            </motion.li>
          ))}
        </motion.ul>
      )}
    </div>
  );
}
