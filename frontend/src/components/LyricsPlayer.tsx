import { Fragment, memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Cue } from "../lib/types";
import { applyCasing, clock } from "../lib/format";
import { Icon } from "./Icon";

const SPEEDS = [0.5, 0.75, 1, 1.25];

interface Props {
  src: string;
  cues: Cue[];
  offsetMs: number;
  casing: string;
  title: string;
  fallbackDuration: number;
  onOffsetChange: (ms: number) => void;
  onEdit: (index: number, roman: string) => Promise<void>;
  onActive?: (cue: Cue | null) => void;
}

/* ---------------------------------------------------------------------------------------- line */
interface LineProps {
  cue: Cue;
  state: "past" | "active" | "future";
  time: number;               // only meaningful for the active line (0 otherwise)
  offset: number;
  casing: string;
  showUrdu: boolean;
  editing: boolean;
  onSeek: (t: number) => void;
  onStartEdit: (i: number) => void;
  onCancelEdit: () => void;
  onSave: (i: number, text: string) => Promise<void>;
}

const Line = memo(function Line(p: LineProps) {
  const { cue, state, time, offset } = p;
  const [draft, setDraft] = useState(cue.roman);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { if (p.editing) { setDraft(cue.roman); setErr(null); setTimeout(() => area.current?.focus(), 0); } }, [p.editing, cue.roman]);

  const save = async () => {
    const text = draft.trim();
    if (!text) { setErr("A caption can't be empty."); return; }
    if (text === cue.roman) { p.onCancelEdit(); return; }
    setSaving(true); setErr(null);
    try { await p.onSave(cue.index, text); p.onCancelEdit(); }
    catch (e) { setErr((e as Error).message || "Couldn't save."); }
    finally { setSaving(false); }
  };

  if (p.editing) {
    return (
      <div className="lyric editing" data-index={cue.index}>
        <textarea ref={area} value={draft} rows={2} dir="auto" disabled={saving} maxLength={600}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void save(); }
                    if (e.key === "Escape") p.onCancelEdit();
                    e.stopPropagation();
                  }} />
        {p.showUrdu && <div className="urdu" dir="rtl" lang="ur">{cue.urdu}</div>}
        <div className="edit-actions">
          <span className="muted sm">Enter saves, Esc cancels</span>
          {err && <span className="field-error">{err}</span>}
          <button className="btn sm ghost-light" onClick={p.onCancelEdit} disabled={saving}>Cancel</button>
          <button className="btn sm light" onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save line"}</button>
        </div>
      </div>
    );
  }

  const text = applyCasing(cue.roman, p.casing);
  const words = cue.words.length ? cue.words : [{ t: cue.roman, s: cue.start, e: cue.end, est: true }];
  const flagged = cue.flags.includes("fallback") ? "rough" : cue.flags.includes("check") ? "check" : null;

  return (
    <div className={`lyric ${state}`} data-index={cue.index}>
      <button className="lyric-hit" onClick={() => p.onSeek(cue.start + offset / 1000)}
              aria-label={`Play from line ${cue.index}: ${text}`}>
        <span className="lyric-text" dir="ltr">
          {words.map((w, i) => {
            let fill = state === "past" ? 1 : 0;
            if (state === "active") {
              const s = w.s + offset / 1000, e = w.e + offset / 1000;
              fill = Math.min(1, Math.max(0, (time - s) / Math.max(e - s, 0.05)));
            }
            return (
              <Fragment key={i}>
                <span className="w" style={{ ["--fill" as string]: `${(fill * 100).toFixed(1)}%` }}>
                  <span className="w-base">{applyCasing(w.t, p.casing)}</span>
                  <span className="w-fill" aria-hidden="true">{applyCasing(w.t, p.casing)}</span>
                </span>{" "}
              </Fragment>
            );
          })}
        </span>
        {p.showUrdu && <span className="urdu" dir="rtl" lang="ur">{cue.urdu}</span>}
      </button>
      <div className="lyric-side">
        {flagged && <span className={`tag ${flagged}`} title={flagged === "rough"
          ? "The model failed on this line; this is a rough offline spelling. Please fix it."
          : "The length differs a lot from the Urdu source. Worth a quick look."}>{flagged}</span>}
        {cue.flags.includes("edited") && <span className="tag edited">edited</span>}
        <button className="lyric-edit" onClick={() => p.onStartEdit(cue.index)} aria-label={`Edit line ${cue.index}`}>
          <Icon name="edit" size={15} />
        </button>
      </div>
    </div>
  );
});

/* ------------------------------------------------------------------------------------- player */
export function LyricsPlayer({ src, cues, offsetMs, casing, title, fallbackDuration, onOffsetChange, onEdit, onActive }: Props) {
  const audio = useRef<HTMLAudioElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const raf = useRef<number>(0);
  const userScrolledAt = useRef(0);

  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(fallbackDuration || 0);
  const [speed, setSpeed] = useState(1);
  const [loop, setLoop] = useState(false);
  const [showUrdu, setShowUrdu] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");

  const off = offsetMs / 1000;

  // Active line = the last line that has started. A line that has already ended but whose successor
  // has not started yet stays "active" so the view doesn't jump around during short pauses.
  const activePos = useMemo(() => {
    let a = -1;
    for (let i = 0; i < cues.length; i++) { if (cues[i].start + off <= time + 0.001) a = i; else break; }
    return a;
  }, [cues, time, off]);
  const active = activePos >= 0 ? cues[activePos] : null;
  const inGap = !!active && time > active.end + off + 0.05;

  useEffect(() => { onActive?.(active && !inGap ? active : null); }, [active, inGap, onActive]);

  /* clock: smooth ~60fps while playing, timeupdate otherwise */
  useEffect(() => {
    const a = audio.current;
    if (!a) return;
    const tick = () => {
      setTime(a.currentTime);
      raf.current = requestAnimationFrame(tick);
    };
    const onPlay = () => { setPlaying(true); cancelAnimationFrame(raf.current); raf.current = requestAnimationFrame(tick); };
    const onPause = () => { setPlaying(false); cancelAnimationFrame(raf.current); setTime(a.currentTime); };
    const onTime = () => { if (a.paused) setTime(a.currentTime); };
    const onMeta = () => { if (isFinite(a.duration)) setDuration(a.duration); setLoadState("ready"); };
    const onErr = () => setLoadState("error");
    a.addEventListener("play", onPlay); a.addEventListener("pause", onPause); a.addEventListener("ended", onPause);
    a.addEventListener("timeupdate", onTime); a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("canplay", onMeta); a.addEventListener("error", onErr);
    return () => {
      cancelAnimationFrame(raf.current);
      a.removeEventListener("play", onPlay); a.removeEventListener("pause", onPause); a.removeEventListener("ended", onPause);
      a.removeEventListener("timeupdate", onTime); a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("canplay", onMeta); a.removeEventListener("error", onErr);
    };
  }, [src]);

  useEffect(() => { if (audio.current) audio.current.playbackRate = speed; }, [speed]);

  /* loop the current line */
  useEffect(() => {
    const a = audio.current;
    if (!loop || !a || !active || !playing) return;
    const end = active.end + off;
    if (time >= end) a.currentTime = Math.max(0, active.start + off);
  }, [loop, time, active, playing, off]);

  /* keep the active line centred, unless the user is scrolling by hand */
  useEffect(() => {
    const box = scroller.current;
    if (!box || activePos < 0 || editing !== null) return;
    if (Date.now() - userScrolledAt.current < 2500) return;
    const el = box.querySelector<HTMLElement>(`[data-index="${cues[activePos].index}"]`);
    if (!el) return;
    const target = el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2;
    box.scrollTo({ top: target, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [activePos, cues, editing]);

  const seek = useCallback((t: number) => {
    const a = audio.current;
    if (!a) return;
    a.currentTime = Math.min(Math.max(0, t), isFinite(a.duration) ? a.duration : t);
    setTime(a.currentTime);
    userScrolledAt.current = 0;
  }, []);

  const toggle = useCallback(() => {
    const a = audio.current;
    if (!a || loadState === "error") return;
    if (a.paused) a.play().catch(() => setLoadState("error")); else a.pause();
  }, [loadState]);

  const jump = useCallback((dir: 1 | -1) => {
    if (!cues.length) return;
    let pos = activePos;
    // "previous" first restarts the current line if we are more than 1 s into it
    if (dir === -1 && active && time - (active.start + off) > 1) pos = activePos + 1;
    const next = Math.min(cues.length - 1, Math.max(0, pos + dir));
    seek(cues[next].start + off);
  }, [cues, activePos, active, time, off, seek]);

  /* keyboard shortcuts (ignored while typing) */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === " " && t.tagName !== "BUTTON") { e.preventDefault(); toggle(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); jump(1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); jump(-1); }
      else if (e.key.toLowerCase() === "l") setLoop((v) => !v);
      else if (e.key === ",") onOffsetChange(Math.max(-2000, offsetMs - 50));
      else if (e.key === ".") onOffsetChange(Math.min(2000, offsetMs + 50));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, jump, offsetMs, onOffsetChange]);

  const save = useCallback((i: number, t: string) => onEdit(i, t), [onEdit]);
  const cancelEdit = useCallback(() => setEditing(null), []);

  const total = duration || fallbackDuration || 0;

  return (
    <section className="stage" aria-label="Caption preview player">
      <audio ref={audio} src={src} preload="auto" />
      <header className="stage-head">
        <div className="stage-title">
          <span className="stage-cover"><Icon name="music" size={20} /></span>
          <div><h2 title={title}>{title}</h2><p>{cues.length} lines</p></div>
        </div>
        <label className="stage-switch">
          <input type="checkbox" checked={showUrdu} onChange={(e) => setShowUrdu(e.target.checked)} />
          <span>Show Urdu</span>
        </label>
      </header>

      <div className="lyrics" ref={scroller}
           onWheel={() => { userScrolledAt.current = Date.now(); }}
           onTouchMove={() => { userScrolledAt.current = Date.now(); }}>
        <div className="lyrics-pad" />
        {cues.map((c, i) => (
          <Line key={c.index} cue={c}
                state={i < activePos ? "past" : i === activePos ? (inGap ? "past" : "active") : "future"}
                time={i === activePos ? time : 0} offset={off} casing={casing} showUrdu={showUrdu}
                editing={editing === c.index} onSeek={seek} onStartEdit={setEditing}
                onCancelEdit={cancelEdit} onSave={save} />
        ))}
        <div className="lyrics-pad" />
      </div>

      {loadState === "error" && (
        <div className="stage-error" role="alert">
          <Icon name="alert" size={16} /> The preview audio couldn't be loaded. Reload the page; if it persists, upload the file again.
        </div>
      )}

      <footer className="controls">
        <div className="seek">
          <span className="t">{clock(time)}</span>
          <input type="range" min={0} max={total || 1} step={0.01} value={Math.min(time, total || 1)}
                 aria-label="Seek" disabled={loadState === "error"}
                 style={{ ["--p" as string]: `${total ? (Math.min(time, total) / total) * 100 : 0}%` }}
                 onChange={(e) => seek(Number(e.target.value))} />
          <span className="t">{clock(total)}</span>
        </div>
        <div className="transport">
          <div className="side-left">
            <button className={`ctl${loop ? " on" : ""}`} onClick={() => setLoop(!loop)} aria-pressed={loop}
                    title="Loop the current line (L)"><Icon name="loop" size={18} /><span>Loop line</span></button>
          </div>
          <div className="mid">
            <button className="ctl round" onClick={() => jump(-1)} aria-label="Previous line" title="Previous line (←)"><Icon name="prev" size={18} /></button>
            <button className="play" onClick={toggle} aria-label={playing ? "Pause" : "Play"} title="Play / pause (Space)"
                    disabled={loadState === "error"}>
              <Icon name={playing ? "pause" : "play"} size={24} />
            </button>
            <button className="ctl round" onClick={() => jump(1)} aria-label="Next line" title="Next line (→)"><Icon name="next" size={18} /></button>
          </div>
          <div className="side-right">
            <div className="speed" role="radiogroup" aria-label="Playback speed">
              {SPEEDS.map((s) => (
                <button key={s} role="radio" aria-checked={speed === s} className={speed === s ? "on" : ""}
                        onClick={() => setSpeed(s)}>{s}×</button>
              ))}
            </div>
          </div>
        </div>
        <p className="shortcuts"><Icon name="keyboard" size={14} /> Space plays, arrow keys change line, L loops, comma and period nudge timing</p>
      </footer>
    </section>
  );
}
