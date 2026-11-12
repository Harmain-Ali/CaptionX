import type { Health, Job, JobSummary, ModelList, SettingsPublic, Cue } from "./types";

export class ApiError extends Error {
  code: string;
  hint?: string | null;
  status: number;
  fields?: Record<string, string>;
  stage?: string | null;
  constructor(code: string, message: string, status = 0, hint?: string | null,
              fields?: Record<string, string>, stage?: string | null) {
    super(message);
    this.code = code; this.status = status; this.hint = hint; this.fields = fields; this.stage = stage;
  }
}

const OFFLINE = new ApiError(
  "BACKEND_OFFLINE",
  "Can't reach the backend.",
  0,
  "Start it with run.sh / run.bat (or: cd backend && python run.py) and reload this page.",
);

function toApiError(status: number, body: any): ApiError {
  const e = body?.error;
  if (e) return new ApiError(e.code ?? "ERROR", e.message ?? "Request failed", status, e.hint, e.fields, e.stage);
  return new ApiError("HTTP_" + status, `Request failed (${status}).`, status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw OFFLINE;
  }
  let body: any = null;
  try { body = await res.json(); } catch { /* non-JSON error page (e.g. proxy 502) */ }
  if (!res.ok) {
    if (res.status === 502 || res.status === 504) throw OFFLINE;
    throw toApiError(res.status, body);
  }
  return body as T;
}

export interface ExportOpts {
  format: string; script: string; offset_ms: number; casing: string; fps?: string; resolution?: string;
}
function exportQuery(o: ExportOpts, download: boolean): string {
  const p = new URLSearchParams({ format: o.format, script: o.script, offset_ms: String(o.offset_ms),
                                  casing: o.casing, download: String(download) });
  if (o.format === "fcpxml" || o.format === "fusion" || o.format === "drt") {
    if (o.fps) p.set("fps", o.fps);
    if (o.resolution) p.set("resolution", o.resolution);
  }
  return p.toString();
}

const json = (method: string, data: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

export const api = {
  health: () => request<Health>("/api/health"),
  settings: () => request<SettingsPublic>("/api/settings"),
  saveSettings: (patch: Record<string, unknown>) => request<SettingsPublic>("/api/settings", json("PUT", patch)),
  resetSettings: () => request<SettingsPublic>("/api/settings/reset", { method: "POST" }),
  defaultPrompt: () => request<{ prompt: string }>("/api/settings/default-prompt"),
  testKey: (apiKey?: string) =>
    request<{ ok: boolean; model_count: number }>("/api/settings/test-key", json("POST", { api_key: apiKey || null })),
  models: () => request<ModelList>("/api/models"),

  jobs: () => request<{ jobs: JobSummary[] }>("/api/jobs"),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  deleteJob: (id: string) => request<{ ok: boolean }>(`/api/jobs/${id}`, { method: "DELETE" }),
  deleteAllJobs: () => request<{ deleted: number }>("/api/jobs", { method: "DELETE" }),
  cancel: (id: string) => request<{ ok: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  reprocess: (id: string, overrides: Record<string, unknown>) =>
    request<{ id: string }>(`/api/jobs/${id}/reprocess`, json("POST", { overrides })),
  editCues: (id: string, edits: { index: number; roman: string }[]) =>
    request<{ cues: Cue[] }>(`/api/jobs/${id}/cues`, json("PUT", { edits })),
  setOptions: (id: string, opts: { offset_ms?: number; casing?: string }) =>
    request<{ ok: boolean }>(`/api/jobs/${id}/options`, json("PUT", opts)),

  audioUrl: (id: string) => `/api/jobs/${id}/audio`,
  exportUrl: (id: string, o: ExportOpts) => `/api/jobs/${id}/export?${exportQuery(o, true)}`,

  exportText: async (id: string, o: ExportOpts) => {
    let res: Response;
    try { res = await fetch(`/api/jobs/${id}/export?${exportQuery(o, false)}`); }
    catch { throw OFFLINE; }
    if (!res.ok) throw new ApiError("EXPORT_FAILED", "Couldn't build the file.", res.status);
    return res.text();
  },

  /** multipart upload with progress (fetch can't report upload progress) */
  upload(file: File, overrides: Record<string, unknown>, onProgress: (p: number) => void,
         signal?: AbortSignal): Promise<{ id: string }> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/jobs");
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
      xhr.onerror = () => reject(OFFLINE);
      xhr.onabort = () => reject(new ApiError("ABORTED", "Upload cancelled."));
      xhr.onload = () => {
        let body: any = null;
        try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
        if (xhr.status >= 200 && xhr.status < 300) return resolve(body);
        if (xhr.status === 502 || xhr.status === 504) return reject(OFFLINE);
        reject(toApiError(xhr.status, body));
      };
      signal?.addEventListener("abort", () => xhr.abort());
      const fd = new FormData();
      fd.append("file", file);
      fd.append("overrides", JSON.stringify(overrides));
      xhr.send(fd);
    });
  },
};
