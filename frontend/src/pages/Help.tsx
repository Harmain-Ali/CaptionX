import { motion } from "motion/react";
import { CREATOR } from "../lib/links";
import { FORMATS } from "../lib/formats";
import { itemVariants, listVariants } from "../lib/motion";
import { Disclosure } from "../components/Disclosure";
import { Icon } from "../components/Icon";
import { Logo } from "../components/Brand";

const QUICK = [
  { t: "Add your key", d: "Open Settings, paste your free Groq key from console.groq.com/keys, press Test key, then Save." },
  { t: "Drop a file", d: "In Studio drop a reel or voice-over (MP3, WAV, M4A, MP4, MOV, MKV, WEBM). Press Generate captions." },
  { t: "Check the timing", d: "Press play. Words fill in as they are spoken. Click any line to jump to it. Use the timing nudge if everything is early or late." },
  { t: "Fix and export", d: "Hover a line and press the pencil to fix a spelling. Pick a format in Export, download, and follow the short steps shown under it." },
];

const KEYS: [string, string][] = [
  ["Space", "Play or pause"], ["← →", "Previous or next line"], ["L", "Loop the current line"], [", .", "Move timing 50 ms earlier or later"],
];

const TROUBLE: [string, string][] = [
  ["Backend not running", "Start it with run.sh (macOS and Linux) or run.bat (Windows). The page reconnects by itself."],
  ["ffmpeg isn't installed", "Windows: winget install Gyan.FFmpeg. macOS: brew install ffmpeg. Linux: sudo apt install ffmpeg. Then restart the app."],
  ["Rate limit reached", "Groq's free tier has caps. Wait the time shown, or switch the Romanization model in Settings (each model has its own quota)."],
  ["Model unavailable", "Groq retires models now and then. In Settings press Refresh models, pick another, Save, then Retry on the failed job."],
  ["Captions are early or late", "Use the Timing nudge in Studio, or the , and . keys. The export follows it."],
  ["Spellings are inconsistent", "Add rules to the Glossary in Settings, lower the model temperature, and keep the 120B model."],
];

export function Help() {
  return (
    <div className="narrow wide">
      <div className="page-head"><div><h1>Help</h1><p className="muted lead">How captionX works, and what every export is for.</p></div></div>

      <motion.section className="card panel" variants={listVariants} initial="initial" animate="animate">
        <h2>Quick start</h2>
        <ol className="how">
          {QUICK.map((q) => (
            <motion.li key={q.t} variants={itemVariants}><div><b>{q.t}</b><p className="muted">{q.d}</p></div></motion.li>
          ))}
        </ol>
      </motion.section>

      <section className="card panel">
        <h2>Export formats</h2>
        <p className="muted">Pick the one that fits how you edit. When in doubt, use SRT.</p>
        <div className="fmt-list">
          {FORMATS.map((f) => (
            <Disclosure key={f.id} className="fmt-item"
              head={<><span className="ext">{f.ext}</span><span className="fmt-name"><b>{f.name}</b><span className="muted"> · {f.tagline}</span></span></>}>
              <p>{f.bestFor}</p>
              {f.timeline && <p className="muted sm">Set the frame rate and size in Export to match your timeline.</p>}
              <ol className="steps-list">{f.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            </Disclosure>
          ))}
        </div>
      </section>

      <section className="card panel">
        <h2>How it works</h2>
        <p className="muted">Your audio is prepared on this computer, sent to Groq's Whisper model for the Urdu text and word timings, then a language model rewrites each line in Roman Urdu. Whisper owns the timing; the language model only spells, so timestamps never drift.</p>
        <div className="flow" aria-label="Pipeline">
          {["Audio or video", "Whisper", "Caption lines", "Roman Urdu", "Export"].map((s, i, a) => (
            <span key={s} className="flow-step">{s}{i < a.length - 1 && <Icon name="arrow" size={14} />}</span>
          ))}
        </div>
      </section>

      <section className="card panel">
        <h2>Player shortcuts</h2>
        <div className="keys">{KEYS.map(([k, d]) => <div key={k}><kbd>{k}</kbd><span>{d}</span></div>)}</div>
      </section>

      <section className="card panel">
        <h2>Troubleshooting</h2>
        <div className="fmt-list">
          {TROUBLE.map(([q, a]) => <Disclosure key={q} className="fmt-item" head={<b>{q}</b>}><p>{a}</p></Disclosure>)}
        </div>
      </section>

      <section className="card panel about">
        <Logo size={44} />
        <div>
          <h2>captionX</h2>
          <p className="muted">Made by <a href={CREATOR.portfolio} target="_blank" rel="noopener noreferrer">{CREATOR.name}</a>. Everything runs on your computer; only audio and text go to Groq.</p>
          <div className="row wrap" style={{ marginTop: 10 }}>
            <a className="btn sm" href={CREATOR.github} target="_blank" rel="noopener noreferrer"><Icon name="github" size={15} /> GitHub</a>
            <a className="btn sm" href={CREATOR.linkedin} target="_blank" rel="noopener noreferrer"><Icon name="linkedin" size={15} /> LinkedIn</a>
            <a className="btn sm" href={CREATOR.portfolio} target="_blank" rel="noopener noreferrer"><Icon name="globe" size={15} /> Portfolio</a>
          </div>
        </div>
      </section>
    </div>
  );
}
