export function clock(sec: number): string {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function clockMs(sec: number): string {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const ms = Math.round((sec % 1) * 1000);
  return `${clock(sec)}.${String(ms).padStart(3, "0")}`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function ago(ts: number): string {
  const d = Math.max(0, Date.now() / 1000 - ts);
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function applyCasing(text: string, casing: string): string {
  if (casing === "lowercase") return text.toLowerCase();
  if (casing === "uppercase") return text.toUpperCase();
  return text;
}

/** Same rule as the backend exporter: at most 2 lines, split at the space nearest the middle. */
export function wrapBalanced(text: string, maxChars: number): string {
  const t = text.trim();
  if (maxChars <= 0 || t.length <= maxChars || !t.includes(" ")) return t;
  const mid = t.length / 2;
  let best = -1, dist = Infinity;
  for (let i = 0; i < t.length; i++) {
    if (t[i] === " " && Math.abs(i - mid) < dist) { best = i; dist = Math.abs(i - mid); }
  }
  return t.slice(0, best) + "\n" + t.slice(best + 1);
}
