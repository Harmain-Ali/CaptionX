import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { spring } from "../lib/motion";
import { Info } from "./Info";
import type { ModelList, RunConfig } from "../lib/types";
import { Icon } from "./Icon";
import { ModelField, NumberField, SelectField } from "./Fields";

export const LANGUAGES = [
  { value: "ur", label: "Urdu (ur)" },
  { value: "hi", label: "Hindi (hi)" },
  { value: "auto", label: "Auto-detect" },
  { value: "en", label: "English (en)" },
  { value: "pa", label: "Punjabi (pa)" },
  { value: "sd", label: "Sindhi (sd)" },
  { value: "ps", label: "Pashto (ps)" },
];

const CASINGS = [
  { value: "natural", label: "Natural (Aaj hum baat karenge)" },
  { value: "lowercase", label: "lowercase" },
  { value: "uppercase", label: "UPPERCASE" },
];

/** The per-run knobs. `base` = saved defaults; `value` = overrides on top of them. */
export function RunOptions({ base, value, onChange, models, defaultOpen = false, title = "Run options" }: {
  base: Partial<RunConfig>;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
  models: ModelList | null;
  defaultOpen?: boolean;
  title?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const baseMap = base as Record<string, unknown>;
  const eff = <T,>(k: string) => (k in value ? value[k] : baseMap[k]) as T;
  const set = (k: string, v: unknown) => {
    const next = { ...value };
    if (v === baseMap[k]) delete next[k];
    else next[k] = v;
    onChange(next);
  };
  const changed = Object.keys(value).length;
  const invalid = !optionsValid(base, value);

  return (
    <section className="card options">
      <div className="options-bar">
        <button className="options-head" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="options-title"><Icon name="settings" size={16} /> {title}</span>
          <span className="options-sub">
            {changed ? <span className="chip accent">{changed} changed for this run</span>
                     : <span className="muted">Using your saved settings</span>}
          </span>
          <Icon name="chevron" className={`chev${open ? " open" : ""}`} />
        </button>
        <Info>Quick changes for this one run only. Your saved defaults live in Settings and are not touched.</Info>
      </div>
      <AnimatePresence initial={false}>
      {open && (
        <motion.div style={{ overflow: "hidden" }} initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1, transition: { height: spring.smooth, opacity: { duration: 0.2 } } }}
                    exit={{ height: 0, opacity: 0, transition: { height: spring.snappy, opacity: { duration: 0.1 } } }}>
        <div className="options-body">
          <div className="grid">
            <ModelField label="Speech model" value={eff<string>("stt_model")} options={models?.stt ?? []}
                        onChange={(v) => set("stt_model", v)}
                        help="large-v3 = best accuracy · large-v3-turbo = faster" />
            <SelectField label="Spoken language" value={eff<string>("stt_language")} options={LANGUAGES}
                         onChange={(v) => set("stt_language", v)} help="Urdu works best when you force it." />
            <ModelField label="Romanization model" value={eff<string>("llm_model")} options={models?.llm ?? []}
                        onChange={(v) => set("llm_model", v)} help="Bigger model = better spelling." />
            <SelectField label="Letter case" value={eff<string>("casing")} options={CASINGS}
                         onChange={(v) => set("casing", v)} />
            <NumberField label="Max words per line" value={eff<number>("max_words_per_cue")} min={1} max={25}
                         onChange={(v) => set("max_words_per_cue", v)} help="Reels: 3 to 6 reads best." />
            <NumberField label="Max seconds per line" value={eff<number>("max_cue_seconds")} min={0.5} max={15} step={0.5}
                         unit="s" onChange={(v) => set("max_cue_seconds", v)} />
          </div>
          {invalid && <p className="field-error">Fix the highlighted numbers before generating.</p>}
          {changed > 0 && <button className="btn ghost sm" onClick={() => onChange({})}>Reset to saved settings</button>}
        </div>
        </motion.div>
      )}
      </AnimatePresence>
    </section>
  );
}

export function optionsValid(base: Partial<RunConfig>, value: Record<string, unknown>) {
  const num = (k: string, lo: number, hi: number) => {
    const v = (k in value ? value[k] : (base as Record<string, unknown>)[k]) as number;
    return typeof v === "number" && v >= lo && v <= hi;
  };
  return num("max_words_per_cue", 1, 25) && num("max_cue_seconds", 0.5, 15);
}
