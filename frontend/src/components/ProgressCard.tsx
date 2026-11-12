import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { spring } from "../lib/motion";
import type { Job } from "../lib/types";
import { Icon } from "./Icon";

const STEPS: { id: string; label: string }[] = [
  { id: "prepare", label: "Prepare audio" },
  { id: "transcribe", label: "Transcribe (Whisper)" },
  { id: "segment", label: "Shape captions" },
  { id: "romanize", label: "Roman Urdu (LLM)" },
];

export function ProgressCard({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t); }, []);
  const idx = STEPS.findIndex((s) => s.id === job.stage);
  const pct = Math.round(job.progress * 100);
  const elapsed = Math.max(0, Math.round(now / 1000 - job.created_at));

  return (
    <section className="card progress-card" aria-live="polite">
      <div className="progress-top">
        <div>
          <h2>{job.status === "queued" ? "Waiting to start…" : "Working on your captions"}</h2>
          <p className="muted">{job.message} <span className="tnum">{elapsed}s</span></p>
        </div>
        <button className="btn ghost sm" onClick={onCancel}>Cancel</button>
      </div>
      <div className="bar big live" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <motion.i initial={false} animate={{ width: `${Math.max(pct, 3)}%` }} transition={spring.smooth} />
      </div>
      <ol className="steps">
        {STEPS.map((s, i) => {
          const state = i < idx ? "done" : i === idx ? "active" : "todo";
          return (
            <li key={s.id} className={state}>
              <span className="dot">{state === "done" ? <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={spring.bouncy} style={{ display: "grid" }}><Icon name="check" size={13} /></motion.span> : i + 1}</span>
              {s.label}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
