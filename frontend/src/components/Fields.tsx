import { useId, type ReactNode } from "react";
import { LayoutGroup, motion } from "motion/react";
import { spring } from "../lib/motion";
import { Info } from "./Info";

export function Field({ label, help, error, children, wide }: {
  label: string; help?: ReactNode; error?: string; children: ReactNode; wide?: boolean;
}) {
  return (
    <div className={`field${wide ? " wide" : ""}${error ? " has-error" : ""}`}>
      <label className="field-label">{label}{help ? <Info label={`About ${label}`}>{help}</Info> : null}</label>
      {children}
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  );
}

export function NumberField({ label, help, error, value, onChange, min, max, step = 1, unit }: {
  label: string; help?: ReactNode; error?: string; value: number; onChange: (v: number) => void;
  min: number; max: number; step?: number; unit?: string;
}) {
  const id = useId();
  const bad = Number.isNaN(value) || value < min || value > max;
  return (
    <Field label={label} help={<>{help ? <>{help} </> : null}<span className="tip-range">Range {min} to {max}{unit ? " " + unit : ""}.</span></>}
           error={error ?? (bad ? `Must be between ${min} and ${max}` : undefined)}>
      <div className="num">
        <input id={id} type="number" value={Number.isNaN(value) ? "" : value} min={min} max={max} step={step}
               aria-invalid={bad} onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))} />
        {unit && <span className="unit">{unit}</span>}
      </div>
    </Field>
  );
}

export function SelectField({ label, help, error, value, onChange, options }: {
  label: string; help?: ReactNode; error?: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <Field label={label} help={help} error={error}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </Field>
  );
}

/** Text input with suggestions: pick from the live model list or type any model id. */
export function ModelField({ label, help, error, value, onChange, options }: {
  label: string; help?: ReactNode; error?: string; value: string; onChange: (v: string) => void; options: string[];
}) {
  const id = useId();
  return (
    <Field label={label} help={help} error={error}>
      <input list={id} value={value} spellCheck={false} onChange={(e) => onChange(e.target.value.trim())} />
      <datalist id={id}>{options.map((o) => <option key={o} value={o} />)}</datalist>
    </Field>
  );
}

export function Toggle({ label, help, checked, onChange }: {
  label: string; help?: ReactNode; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="field toggle-field">
      <label className="toggle">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="track"><span className="thumb" /></span>
        <span className="field-label inline">{label}</span>
      </label>
      {help && <Info label={`About ${label}`}>{help}</Info>}
    </div>
  );
}

/** Pill that slides between options on a spring. */
export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string; title?: string }[]; label: string;
}) {
  const gid = useId();
  return (
    <LayoutGroup id={gid}>
      <div className="segmented" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button key={o.value} type="button" role="radio" aria-checked={value === o.value} title={o.title}
                  className={value === o.value ? "on" : ""} onClick={() => onChange(o.value)}>
            {value === o.value && <motion.span layoutId="seg" className="seg-pill" transition={spring.snappy} />}
            <span className="seg-label">{o.label}</span>
          </button>
        ))}
      </div>
    </LayoutGroup>
  );
}
