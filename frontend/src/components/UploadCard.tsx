import { useRef, useState } from "react";
import { motion } from "motion/react";
import { spring } from "../lib/motion";
import { bytes } from "../lib/format";
import { Icon } from "./Icon";

export const ACCEPT = ".mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.webm,.wma,.mp4,.mov,.mkv,.avi,.m4v,.mpeg,.mpg,.3gp";
const EXT = new Set(ACCEPT.split(",").map((s) => s.trim()));

export function checkFile(f: File, maxMb: number): string | null {
  const ext = "." + (f.name.split(".").pop() ?? "").toLowerCase();
  if (f.size === 0) return "That file is empty (0 bytes).";
  if (!EXT.has(ext)) return `“${ext}” isn't a supported audio/video type. Use MP3, WAV, M4A, MP4, MOV, MKV, WEBM, FLAC or OGG.`;
  if (f.size > maxMb * 1024 * 1024) return `That file is ${bytes(f.size)}; your limit is ${maxMb} MB (change it in Settings).`;
  return null;
}

export function UploadCard({ file, onFile, disabled, maxMb, progress }: {
  file: File | null; onFile: (f: File | null) => void; disabled?: boolean; maxMb: number; progress?: number | null;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const take = (f: File | undefined | null) => {
    if (!f) return;
    const p = checkFile(f, maxMb);
    setProblem(p);
    onFile(p ? null : f);
  };

  if (file) {
    return (
      <motion.div className="file-chip card" initial={{ opacity: 0, scale: 0.94, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={spring.bouncy}>
        <div className="file-icon"><Icon name={/\.(mp4|mov|mkv|avi|m4v|webm|3gp)$/i.test(file.name) ? "film" : "music"} size={22} /></div>
        <div className="file-info">
          <b title={file.name}>{file.name}</b>
          <span className="muted">{bytes(file.size)}</span>
          {progress != null && (
            <div className="bar" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
              <i style={{ width: `${progress * 100}%` }} />
            </div>
          )}
        </div>
        {!disabled && <button className="icon-btn" aria-label="Remove file" onClick={() => { onFile(null); setProblem(null); }}><Icon name="x" /></button>}
      </motion.div>
    );
  }

  return (
    <>
      <motion.div className={`drop${drag ? " over" : ""}${problem ? " bad" : ""}`}
           animate={{ scale: drag ? 1.015 : 1 }} whileTap={{ scale: 0.99 }} transition={spring.snappy}
           role="button" tabIndex={0} aria-label="Choose an audio or video file"
           onClick={() => input.current?.click()}
           onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
           onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
           onDragLeave={() => setDrag(false)}
           onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files?.[0]); }}>
        <div className="drop-icon"><Icon name="upload" size={26} /></div>
        <h2>Drop your reel or audio here</h2>
        <p className="muted">or click to browse. MP3, WAV, M4A, MP4, MOV, MKV or WEBM, up to {maxMb} MB.</p>
        <input ref={input} type="file" accept={ACCEPT} hidden
               onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
      </motion.div>
      {problem && <p className="field-error" role="alert">{problem}</p>}
    </>
  );
}
