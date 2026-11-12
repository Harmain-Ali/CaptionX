import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Health } from "./types";

interface Ctx { health: Health | null; offline: boolean; refresh: () => void }
const C = createContext<Ctx>({ health: null, offline: false, refresh: () => {} });
export const useHealth = () => useContext(C);

export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const refresh = useCallback(async () => {
    try { setHealth(await api.health()); setOffline(false); } catch { setOffline(true); }
  }, []);
  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, [refresh]);
  return <C.Provider value={{ health, offline, refresh }}>{children}</C.Provider>;
}
