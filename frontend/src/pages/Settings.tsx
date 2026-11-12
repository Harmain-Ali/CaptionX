import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "../lib/api";
import { useHealth } from "../lib/health";
import type { ModelList, SettingsPublic } from "../lib/types";
import { ErrorPanel } from "../components/ErrorPanel";
import { Field, ModelField, NumberField, SelectField, Toggle } from "../components/Fields";
import { LANGUAGES } from "../components/RunOptions";
import { FPS_OPTIONS, SIZE_OPTIONS, withValue } from "../lib/resolve";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toast";

// Mirrors the backend limits so mistakes are caught before saving.
const LIMITS: Record<string, [number, number]> = {
  stt_temperature: [0, 1], llm_temperature: [0, 1], llm_batch_size: [1, 80], llm_max_tokens: [256, 32768],
  max_words_per_cue: [1, 25], max_cue_seconds: [0.5, 15], min_cue_seconds: [0.1, 5], gap_break_seconds: [0.1, 5],
  linger_ms: [0, 1500], max_chars_per_line: [0, 80], timing_offset_ms: [-2000, 2000],
  chunk_seconds: [60, 1800], max_upload_mb: [1, 4000], max_duration_minutes: [1, 240],
  request_timeout_s: [10, 600], max_retries: [0, 8],
  fcpxml_font_size: [10, 400], fcpxml_position_y: [0.05, 0.95],
};
const META = new Set(["groq_api_key_set", "groq_api_key_masked", "groq_api_key_source"]);

function Section({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section className="card settings-section">
      <h2>{title}</h2>
      {intro && <p className="muted intro-p">{intro}</p>}
      {children}
    </section>
  );
}

export function Settings() {
  const toast = useToast();
  const { refresh } = useHealth();
  const [saved, setSaved] = useState<SettingsPublic | null>(null);
  const [draft, setDraft] = useState<SettingsPublic | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [models, setModels] = useState<ModelList | null>(null);
  const [modelsBusy, setModelsBusy] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [keyMsg, setKeyMsg] = useState<{ ok: boolean; text: string; hint?: string | null } | null>(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});

  const loadModels = useCallback(async () => {
    setModelsBusy(true);
    try { setModels(await api.models()); } catch { /* shows fallback text */ } finally { setModelsBusy(false); }
  }, []);

  useEffect(() => {
    api.settings().then((s) => { setSaved(s); setDraft(s); }).catch((e) => setLoadError(e as ApiError));
    void loadModels();
  }, [loadModels]);

  const set = (k: string, v: unknown) => {
    setDraft((d) => (d ? { ...d, [k]: v } : d));
    setServerErrors((e) => { if (!(k in e)) return e; const n = { ...e }; delete n[k]; return n; });
  };

  const changed = useMemo(() => {
    if (!saved || !draft) return {} as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(draft)) if (!META.has(k) && draft[k] !== saved[k]) out[k] = draft[k];
    return out;
  }, [saved, draft]);

  const problems = useMemo(() => {
    const p: Record<string, string> = {};
    if (!draft) return p;
    for (const [k, [lo, hi]] of Object.entries(LIMITS)) {
      const v = draft[k] as number;
      if (typeof v !== "number" || Number.isNaN(v) || v < lo || v > hi) p[k] = `Must be between ${lo} and ${hi}`;
    }
    if (!p.min_cue_seconds && !p.max_cue_seconds && draft.min_cue_seconds > draft.max_cue_seconds)
      p.min_cue_seconds = "Can't be longer than the maximum line length";
    if (!draft.stt_model.trim()) p.stt_model = "Required";
    if (!draft.llm_model.trim()) p.llm_model = "Required";
    const sp = draft.system_prompt.trim();
    if (sp && !/cues/.test(sp)) p.system_prompt = "Your prompt must tell the model to reply with JSON in the form {\"cues\":[{\"id\":1,\"roman\":\"…\"}]}, otherwise the app can't read the answer.";
    return p;
  }, [draft]);

  const hasKeyChange = keyInput.trim().length > 0;
  const dirty = Object.keys(changed).length > 0 || hasKeyChange;
  const invalid = Object.keys(problems).length > 0;

  const testKey = async () => {
    setTesting(true); setKeyMsg(null);
    try {
      const r = await api.testKey(keyInput.trim() || undefined);
      setKeyMsg({ ok: true, text: `Key works. ${r.model_count} models available.` });
      void loadModels();
    } catch (e) {
      const err = e as ApiError;
      setKeyMsg({ ok: false, text: err.message, hint: err.hint });
    } finally { setTesting(false); }
  };

  const save = async () => {
    if (!dirty || invalid) return;
    setSaving(true);
    try {
      const patch: Record<string, unknown> = { ...changed };
      if (hasKeyChange) patch.groq_api_key = keyInput.trim();
      const s = await api.saveSettings(patch);
      setSaved(s); setDraft(s); setKeyInput(""); setServerErrors({});
      toast("Settings saved");
      refresh();
      if (hasKeyChange) void loadModels();
    } catch (e) {
      const err = e as ApiError;
      if (err.fields) setServerErrors(err.fields);
      toast(err.message, "err");
    } finally { setSaving(false); }
  };

  const discard = () => { setDraft(saved); setKeyInput(""); setServerErrors({}); setKeyMsg(null); };

  const removeKey = async () => {
    if (!window.confirm("Remove the saved API key from this computer?")) return;
    try { const s = await api.saveSettings({ clear_api_key: true }); setSaved(s); setDraft((d) => d ? { ...d, ...pickMeta(s) } : s); setKeyInput(""); setKeyMsg(null); toast("Key removed"); refresh(); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  const reset = async () => {
    if (!window.confirm("Reset every setting to its default? Your API key is kept.")) return;
    try { const s = await api.resetSettings(); setSaved(s); setDraft(s); setServerErrors({}); toast("Defaults restored"); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  const loadDefaultPrompt = async () => {
    try { const r = await api.defaultPrompt(); set("system_prompt", r.prompt); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  const wipe = async () => {
    if (!window.confirm("Delete ALL past jobs and their audio from this computer?")) return;
    try { const r = await api.deleteAllJobs(); toast(`Deleted ${r.deleted} job${r.deleted === 1 ? "" : "s"}`); }
    catch (e) { toast((e as Error).message, "err"); }
  };

  if (loadError) return <div className="narrow"><ErrorPanel code={loadError.code} message={loadError.message} hint={loadError.hint} /></div>;
  if (!draft || !saved) return <div className="narrow"><div className="skeleton" aria-busy="true" aria-label="Loading settings" /></div>;

  const err = (k: string) => serverErrors[k] ?? problems[k];
  const num = (k: string, label: string, help?: ReactNode, o: { step?: number; unit?: string } = {}) => (
    <NumberField label={label} help={help} value={draft[k] as number} onChange={(v) => set(k, v)}
                 min={LIMITS[k][0]} max={LIMITS[k][1]} step={o.step} unit={o.unit} error={err(k)} />
  );
  const customPrompt = draft.system_prompt.trim().length > 0;

  return (
    <div className="narrow wide settings">
      <div className="page-head"><h1>Settings</h1></div>

      <Section title="Groq API key" intro={<>Free at <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer">console.groq.com/keys</a>, no card needed. The key stays on this computer and is only sent to Groq.</>}>
        <div className="key-status">
          {saved.groq_api_key_set
            ? <span className="tag done"><Icon name="check" size={13} /> {saved.groq_api_key_source === "env" ? "Using GROQ_API_KEY from your environment" : `Saved key ${saved.groq_api_key_masked}`}</span>
            : <span className="tag error">No key yet</span>}
        </div>
        <Field label={saved.groq_api_key_set ? "Replace key" : "Paste your key"} error={undefined}
               help="Leave empty to keep the current key.">
          <div className="key-input">
            <input type={showKey ? "text" : "password"} value={keyInput} placeholder="gsk_…" autoComplete="off" spellCheck={false}
                   onChange={(e) => { setKeyInput(e.target.value); setKeyMsg(null); }} />
            <button type="button" className="icon-btn" onClick={() => setShowKey(!showKey)} aria-label={showKey ? "Hide key" : "Show key"}>
              <Icon name={showKey ? "eyeoff" : "eye"} size={17} />
            </button>
          </div>
        </Field>
        {keyInput.trim() && !keyInput.trim().startsWith("gsk_") && <p className="field-error">Groq keys usually start with “gsk_”. Double-check what you pasted.</p>}
        <div className="row">
          <button className="btn sm" onClick={testKey} disabled={testing || (!keyInput.trim() && !saved.groq_api_key_set)}>
            {testing ? "Testing…" : "Test key"}
          </button>
          {saved.groq_api_key_source === "settings" && <button className="btn ghost sm danger-text" onClick={removeKey}>Remove saved key</button>}
        </div>
        {keyMsg && (
          <p className={keyMsg.ok ? "key-ok" : "field-error"} role="status">
            {keyMsg.text}{keyMsg.hint ? ` ${keyMsg.hint}` : ""}
          </p>
        )}
      </Section>

      <Section title="Models" intro="Defaults: Whisper large-v3 for accuracy, and GPT-OSS 120B for clean Roman Urdu spelling. Groq retires models from time to time. If one stops working, press Refresh models and pick another.">
        <div className="grid">
          <ModelField label="Speech-to-text model" value={draft.stt_model} options={models?.stt ?? []} error={err("stt_model")}
                      onChange={(v) => set("stt_model", v)} help="whisper-large-v3 is the most accurate. large-v3-turbo is faster but slips more on Urdu." />
          <ModelField label="Roman Urdu model" value={draft.llm_model} options={models?.llm ?? []} error={err("llm_model")}
                      onChange={(v) => set("llm_model", v)} help="openai/gpt-oss-120b spells best. openai/gpt-oss-20b is faster but makes more mistakes." />
        </div>
        <div className="row">
          <button className="btn sm" onClick={loadModels} disabled={modelsBusy}><Icon name="refresh" size={15} /> {modelsBusy ? "Loading…" : "Refresh models"}</button>
          <span className="muted sm">
            {models?.source === "live" ? `Live list from Groq: ${models.stt.length} speech, ${models.llm.length} chat models.`
              : models?.warning ?? "Showing a built-in list."}
          </span>
        </div>
      </Section>

      <Section title="Transcription">
        <div className="grid">
          <SelectField label="Spoken language" value={draft.stt_language} options={LANGUAGES} onChange={(v) => set("stt_language", v)}
                       help="Forcing Urdu avoids Whisper guessing Hindi for short clips." />
          {num("stt_temperature", "Whisper temperature", "0 is the most stable. Raise only if Whisper gets stuck.", { step: 0.1 })}
        </div>
        <Field label="Vocabulary hint" wide help="Optional. Names and terms Whisper should spell right, e.g. “FANN, Heptagram AI, DaVinci Resolve”. Max about 200 characters.">
          <textarea rows={2} value={draft.stt_prompt} maxLength={400} onChange={(e) => set("stt_prompt", e.target.value)} />
        </Field>
        <Toggle label="Remove Whisper hallucinations" checked={draft.filter_hallucinations} onChange={(v) => set("filter_hallucinations", v)}
                help="Drops invented text over silence and repetition loops (“thanks for watching” ×5)." />
      </Section>

      <Section title="Roman Urdu writing">
        <div className="grid">
          {num("llm_temperature", "Model temperature", "Low = consistent spelling.", { step: 0.05 })}
          {num("llm_batch_size", "Phrases per request", "A reel fits in one request, even with one word per line. Lower it if the model drops lines.")}
          {num("llm_max_tokens", "Max reply tokens", "Raise for very long batches.")}
          <SelectField label="Letter case" value={draft.casing} onChange={(v) => set("casing", v)}
                       options={[{ value: "natural", label: "Natural (Aaj hum baat karenge)" }, { value: "lowercase", label: "lowercase" }, { value: "uppercase", label: "UPPERCASE" }]} />
        </div>
        <Toggle label="Remove punctuation" checked={draft.strip_punctuation} onChange={(v) => set("strip_punctuation", v)}
                help="Commas, full stops and question marks are dropped. Popular for bold reel captions." />
        <Field label="Glossary" wide error={err("glossary")}
               help={<>One rule per line, written <code>source =&gt; output</code>. The model always applies it, e.g. <code>فن =&gt; FANN</code> or <code>ہیپٹاگرام =&gt; Heptagram</code>.</>}>
          <textarea rows={4} value={draft.glossary} dir="auto" spellCheck={false} placeholder={"فن => FANN\nڈاونچی ریزالو => DaVinci Resolve"}
                    onChange={(e) => set("glossary", e.target.value)} />
        </Field>

        <Field label="Master prompt" wide error={err("system_prompt")}
               help="The instructions the model follows. Empty means the built-in prompt, which is tuned for Pakistani Roman Urdu with strict JSON output.">
          <div className="prompt-bar">
            <span className={`tag ${customPrompt ? "running" : "done"}`}>{customPrompt ? "Custom prompt" : "Built-in prompt"}</span>
            {!customPrompt && <button className="btn sm" onClick={loadDefaultPrompt}><Icon name="edit" size={14} /> View and edit</button>}
            {customPrompt && <button className="btn sm" onClick={() => set("system_prompt", "")}>Go back to built-in</button>}
          </div>
          {customPrompt && (
            <textarea className="prompt" rows={20} value={draft.system_prompt} spellCheck={false}
                      onChange={(e) => set("system_prompt", e.target.value)} />
          )}
          {customPrompt && <p className="field-help">Placeholders <code>{"{{CASING_RULE}}"}</code>, <code>{"{{PUNCTUATION_RULE}}"}</code> and <code>{"{{GLOSSARY_BLOCK}}"}</code> are filled in from the settings above.</p>}
        </Field>
      </Section>

      <Section title="Caption timing" intro="How Whisper's text is cut into lines. Reels read best with 3 to 6 words and under 3 seconds per line.">
        <div className="grid">
          {num("max_words_per_cue", "Max words per line")}
          {num("max_cue_seconds", "Max seconds per line", undefined, { step: 0.5, unit: "s" })}
          {num("min_cue_seconds", "Min seconds on screen", "Short lines are held this long.", { step: 0.1, unit: "s" })}
          {num("gap_break_seconds", "Start a new line after a pause of", undefined, { step: 0.1, unit: "s" })}
          {num("linger_ms", "Keep lines visible a bit longer", "Added to every line if there's room.", { step: 10, unit: "ms" })}
          {num("max_chars_per_line", "Wrap at characters", "Long lines split into two. 0 turns wrapping off.", { unit: "chars" })}
          {num("timing_offset_ms", "Default timing offset", "Negative shows captions earlier.", { step: 10, unit: "ms" })}
        </div>
      </Section>

      <Section title="DaVinci Resolve export (Text+ and FCPXML)" intro="Look of the captions in the Text+ file and the .fcpxml file, and the defaults for frame rate and size. You can change frame rate and size per export in the result page.">
        <div className="grid">
          <SelectField label="Frame rate" value={draft.fcpxml_fps} onChange={(v) => set("fcpxml_fps", v)} options={FPS_OPTIONS}
                       help="Must match your Resolve timeline." />
          <SelectField label="Frame size" value={draft.fcpxml_resolution} onChange={(v) => set("fcpxml_resolution", v)}
                       options={withValue(SIZE_OPTIONS, draft.fcpxml_resolution)} />
          <Field label="Font" error={err("fcpxml_font")} help="Use a font installed on the computer that runs Resolve.">
            <input type="text" value={draft.fcpxml_font} spellCheck={false} onChange={(e) => set("fcpxml_font", e.target.value)} />
          </Field>
          <Field label="Font style" error={err("fcpxml_font_face")} help="e.g. Bold, Regular, Black. Leave empty for the default.">
            <input type="text" value={draft.fcpxml_font_face} spellCheck={false} onChange={(e) => set("fcpxml_font_face", e.target.value)} />
          </Field>
          {num("fcpxml_font_size", "Font size", "Tweak in Resolve's Inspector if it looks off.")}
          <NumberField label="Caption height from the top" unit="%" min={5} max={95} step={1}
                       value={Math.round(draft.fcpxml_position_y * 100)} error={err("fcpxml_position_y")}
                       onChange={(v) => set("fcpxml_position_y", v / 100)} help="70 puts captions in the lower third, clear of the Reels buttons." />
          <Field label="Text colour">
            <input className="color" type="color" value={draft.fcpxml_text_color} onChange={(e) => set("fcpxml_text_color", e.target.value.toUpperCase())} />
          </Field>
          <Field label="Outline colour" help="Used by the FCPXML export. Text+ files take their outline from the Inspector in Resolve.">
            <input className="color" type="color" value={draft.fcpxml_outline_color} onChange={(e) => set("fcpxml_outline_color", e.target.value.toUpperCase())} />
          </Field>
        </div>
        <Toggle label="Outline around the text" checked={draft.fcpxml_outline} onChange={(v) => set("fcpxml_outline", v)}
                help="Used by the FCPXML export. Keeps captions readable on bright footage." />
      </Section>

      <Section title="Audio and limits">
        <div className="grid">
          <SelectField label="Audio format sent to Whisper" value={draft.audio_format} onChange={(v) => set("audio_format", v)}
                       options={[{ value: "flac", label: "FLAC (lossless, best accuracy)" }, { value: "mp3", label: "MP3 (smaller uploads)" }]} />
          {num("chunk_seconds", "Split audio every", "Groq accepts about 25 MB per request.", { step: 30, unit: "s" })}
          {num("max_upload_mb", "Max upload size", undefined, { unit: "MB" })}
          {num("max_duration_minutes", "Max duration", undefined, { unit: "min" })}
          {num("request_timeout_s", "Groq request timeout", undefined, { unit: "s" })}
          {num("max_retries", "Retries on errors", "For rate limits and network drops.")}
        </div>
      </Section>

      <Section title="Data">
        <div className="row wrap">
          <button className="btn sm" onClick={reset}>Reset settings to defaults</button>
          <button className="btn sm danger-text" onClick={wipe}><Icon name="trash" size={15} /> Delete all past jobs</button>
        </div>
      </Section>

      <div className={`savebar${dirty ? " show" : ""}`} role="region" aria-label="Unsaved changes">
        <span>{invalid ? "Fix the highlighted fields to save." : "You have unsaved changes."}</span>
        <div className="row">
          <button className="btn ghost sm" onClick={discard} disabled={saving}>Discard</button>
          <button className="btn primary sm" onClick={save} disabled={saving || invalid}>{saving ? "Saving…" : "Save settings"}</button>
        </div>
      </div>
    </div>
  );
}

function pickMeta(s: SettingsPublic) {
  return { groq_api_key_set: s.groq_api_key_set, groq_api_key_masked: s.groq_api_key_masked, groq_api_key_source: s.groq_api_key_source };
}
