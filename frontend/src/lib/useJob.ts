import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { Job } from "./types";

/** Loads a job and polls it while it is queued/running. */
export function useJob(id: string | undefined) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const j = await api.job(id);
      if (!alive.current) return;
      setJob(j);
      setError(null);
      if (j.status === "queued" || j.status === "running") {
        timer.current = window.setTimeout(load, 700);
      }
    } catch (e) {
      if (!alive.current) return;
      const err = e as ApiError;
      setError(err);
      // Backend restarting/offline: keep trying quietly instead of giving up.
      if (err.code === "BACKEND_OFFLINE") timer.current = window.setTimeout(load, 2000);
    }
  }, [id]);

  useEffect(() => {
    alive.current = true;
    setJob(null);
    setError(null);
    load();
    return () => { alive.current = false; window.clearTimeout(timer.current); };
  }, [id, load]);

  const reload = useCallback(() => { window.clearTimeout(timer.current); return load(); }, [load]);
  return { job, setJob, error, reload };
}
