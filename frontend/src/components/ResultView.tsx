import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { FORMATS, formatById, type FormatId } from "../lib/formats";
import { spring } from "../lib/motion";
import { Info } from "./Info";
import { api, ApiError } from "../lib/api";
import { FPS_OPTIONS, SIZE_OPTIONS, withValue } from "../lib/resolve";
import type { Cue, Job, ModelList } from "../lib/types";
import { LyricsPlayer } from "./LyricsPlayer";
import { PhonePreview } from "./PhonePreview";
import { RunOptions, optionsValid } from "./RunOptions";
import { Segmented } from "./Fields";
import { Icon } from "./Icon";
import { useToast } from "./Toast";
import { go, href } from "../lib/router";
import type { Casing } from "../lib/types";

export function ResultView({ job, models, reload }: { job: Job; models: ModelList | null; reload: () => Promise<void> }) {
  const toast = useToast();
  const [cues, setCues] = useState<Cue[]>(job.cues ?? []);
  const [offset, setOffset] = useState(job.offset_ms ?? 0);
  const [casing, setCasing] = useState<Casing>(job.casing ?? "natural");
  const [format, setFormat] = useState<FormatId>("srt");
  const [fps, setFps] = useState("30");
  const [size, setSize] = useState("1080x1920");
  const [script, setScript] = useState<"roman" | "urdu" | "both">("roman");
  const [nowText, setNowText] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const saveTimer = useRef<number | undefined>(undefined);

  useEffect(() => { setCues(job.cues ?? []); setOffset(job.offset_ms ?? 0); setCasing(job.casing ?? "natural"); }, [job.id, job.cues, job.offset_ms, job.casing]);
  useEffect(() => () => window.clearTimeout(saveTimer.current), []);
  useEffect(() => {  // start from the frame rate / size saved in Settings
    api.settings().then((s) => { setFps(s.fcpxml_fps); setSize(s.fcpxml_resolution); }).catch(() => {});
  }, []);

  const persist = useCallback((o: { offset_ms?: number; casing?: string }) => {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => { api.setOptions(job.id, o).catch(() => { /* non-critical */ }); }, 400);
  }, [job.id]);

  const changeOffset = useCallback((ms: number) => {
    const v = Math.max(-2000, Math.min(2000, Math.round(ms)));
    setOffset(v); persist({ offset_ms: v });
  }, [persist]);

  const changeCasing = (c: Casing) => { setCasing(c); persist({ casing: c }); };

  const onEdit = useCallback(async (index: number, roman: string) => {
    const r = await api.editCues(job.id, [{ index, roman }]);
    setCues(r.cues);
  }, [job.id]);

  const onActive = useCallback((c: Cue | null) => setNowText(c ? c.roman : null), []);

  const cur = formatById(format);
  const exportOpts = { format, script, offset_ms: offset, casing, fps, resolution: size };

  const copy = async () => {
    try {
      const text = await api.exportText(job.id, exportOpts);
      await navigator.clipboard.writeText(text);
      toast(`Copied ${format.toUpperCase()} to the clipboard`);
    } catch (e) {
      toast((e as Error).message || "Couldn't copy. Use Download instead.", "err");
    }
  };

  const regenerate = async () => {
    if (cues.some((c) => c.flags.includes("edited")) &&
        !window.confirm("Regenerating replaces every line, including the ones you edited. Continue?")) return;
    setBusy(true);
    try {
      await api.reprocess(job.id, overrides);
      setOverrides({});
      await reload();
    } catch (e) {
      const err = e as ApiError;
      const first = err.fields ? Object.entries(err.fields)[0] : null;
      toast(first ? `${first[0]}: ${first[1]}` : err.message, "err");
    } finally { setBusy(false); }
  };

  const del = async () => {
    if (!window.confirm("Delete this job and its audio from this computer?")) return;
    try { await api.deleteJob(job.id); toast("Deleted"); go(href.studio); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  const s = job.stats;
  const maxChars = job.config.max_chars_per_line as number;

  return (
    <div className="result">
      {job.warnings.length > 0 && (
        <div className="warnings" role="status">
          {job.warnings.map((w, i) => <p key={i}><Icon name="alert" size={16} /> {w}</p>)}
        </div>
      )}

      <div className="result-grid">
        <LyricsPlayer src={api.audioUrl(job.id)} cues={cues} offsetMs={offset} casing={casing}
                      title={job.filename} fallbackDuration={job.duration ?? 0}
                      onOffsetChange={changeOffset} onEdit={onEdit} onActive={onActive} />

        <aside className="side">
          <section className="card panel preview-panel">
            <PhonePreview text={nowText} casing={casing} maxChars={maxChars} />
            <div className="timing">
              <div className="row"><h3>Timing</h3><Info>Shifts every caption earlier (minus) or later (plus). The preview and the exported file both follow it.</Info></div>
              
              <div className="nudge">
                <button className="btn sm" onClick={() => changeOffset(offset - 50)} aria-label="Captions 50 milliseconds earlier">−50</button>
                <output className="nudge-val" aria-live="polite">{offset > 0 ? "+" : ""}{offset} ms</output>
                <button className="btn sm" onClick={() => changeOffset(offset + 50)} aria-label="Captions 50 milliseconds later">+50</button>
              </div>
              <input type="range" min={-2000} max={2000} step={10} value={offset} aria-label="Timing offset"
                     onChange={(e) => changeOffset(Number(e.target.value))} />
              {offset !== 0 && <button className="btn ghost sm" onClick={() => changeOffset(0)}>Reset to 0</button>}
            </div>
          </section>

          <section className="card panel">
            <div className="row between"><h3>Export</h3>
              <Info>Choose the file type that fits your editor. SRT works almost everywhere. The Text+ options are for DaVinci Resolve. Steps for the chosen format appear below.</Info>
            </div>
            <LayoutGroup id="fmt">
              <div className="fmt-grid" role="radiogroup" aria-label="Format">
                {FORMATS.map((f) => (
                  <button key={f.id} type="button" role="radio" aria-checked={format === f.id}
                          className={`fmt${format === f.id ? " on" : ""}`} onClick={() => setFormat(f.id)}>
                    {format === f.id && <motion.span layoutId="fmt-pill" className="fmt-pill" transition={spring.snappy} />}
                    <span className="fmt-ext">{f.ext}</span>
                    <b>{f.name}</b>
                    <span className="muted sm">{f.tagline}</span>
                  </button>
                ))}
              </div>
            </LayoutGroup>
            <AnimatePresence initial={false}>
              {cur.timeline && (
                <motion.div key="tl" style={{ overflow: "hidden" }} initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1, transition: spring.smooth }}
                            exit={{ height: 0, opacity: 0, transition: { duration: 0.14 } }}>
                  <div className="export-stack">
                    <div className="export-row">
                      <span className="field-label">Frame rate <Info>Must match your Resolve timeline, or captions drift.</Info></span>
                      <select className="mini" value={fps} onChange={(e) => setFps(e.target.value)} aria-label="Frame rate">
                        {withValue(FPS_OPTIONS, fps).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </div>
                    <div className="export-row">
                      <span className="field-label">Frame size <Info>Your timeline resolution, for example 1080x1920 for vertical reels. Font, colour and position come from Settings.</Info></span>
                      <select className="mini" value={size} onChange={(e) => setSize(e.target.value)} aria-label="Frame size">
                        {withValue(SIZE_OPTIONS, size).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
            <div className="export-row">
              <span className="field-label">Script <Info>Roman Urdu, the original Urdu script, or both stacked in each caption.</Info></span>
              <Segmented label="Script" value={script} onChange={setScript}
                         options={[{ value: "roman", label: "Roman" }, { value: "urdu", label: "Urdu" }, { value: "both", label: "Both" }]} />
            </div>
            <div className="export-row">
              <span className="field-label">Letters <Info>Aa keeps natural capitals, aa is all lowercase, AA is all capitals.</Info></span>
              <Segmented label="Letter case" value={casing} onChange={changeCasing}
                         options={[{ value: "natural", label: "Aa" }, { value: "lowercase", label: "aa" }, { value: "uppercase", label: "AA" }]} />
            </div>
            <div className="export-actions">
              <a className="btn primary" href={api.exportUrl(job.id, exportOpts)} download>
                <Icon name="download" size={17} /> Download {cur.ext}
              </a>
              {format !== "drt" && <button className="btn" onClick={copy}><Icon name="copy" size={16} /> Copy</button>}
            </div>
          </section>

          <section className="card panel howto" aria-live="polite">
            <h3><Icon name="film" size={17} /> How to use {cur.name}</h3>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={cur.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0, transition: spring.smooth }}
                          exit={{ opacity: 0, transition: { duration: 0.08 } }}>
                <p className="muted">{cur.bestFor}</p>
                <ol className="steps-list">{cur.steps.map((t, i) => <li key={i}>{t}</li>)}</ol>
              </motion.div>
            </AnimatePresence>
          </section>

          <RunOptions title="Regenerate with other settings" base={job.config} value={overrides}
                      onChange={setOverrides} models={models} />
          <div className="regen">
            <button className="btn" onClick={regenerate} disabled={busy || !optionsValid(job.config, overrides)}>
              <Icon name="refresh" size={16} /> {busy ? "Starting…" : "Regenerate lines"}
            </button>
            <p className="muted sm">Reuses the saved Whisper transcript, so it is fast and doesn't use your speech quota.</p>
          </div>

          <div className="stats">
            {s.stt_seconds != null && <span>Whisper {s.stt_seconds}s</span>}
            {s.llm_seconds != null && <span>Romanizing {s.llm_seconds}s</span>}
            {job.duration != null && <span>Audio {Math.round(job.duration)}s</span>}
            <span>{String(job.config.llm_model)}</span>
          </div>
          <button className="btn ghost sm danger-text" onClick={del}><Icon name="trash" size={15} /> Delete this job</button>
        </aside>
      </div>
    </div>
  );
}
