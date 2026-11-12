import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { spring } from "../lib/motion";
import { Icon } from "./Icon";

type Kind = "ok" | "err" | "info";
interface T { id: number; kind: Kind; text: string }
const Ctx = createContext<(text: string, kind?: Kind) => void>(() => {});
export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<T[]>([]);
  const push = useCallback((text: string, kind: Kind = "ok") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-3), { id, kind, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === "err" ? 7000 : 3500);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div key={t.id} layout className={`toast ${t.kind}`}
                        initial={{ opacity: 0, y: 24, scale: 0.9 }}
                        animate={{ opacity: 1, y: 0, scale: 1, transition: spring.bouncy }}
                        exit={{ opacity: 0, scale: 0.92, x: 40, transition: { duration: 0.16 } }}>
              <Icon name={t.kind === "err" ? "alert" : t.kind === "ok" ? "check" : "info"} size={17} />
              <span>{t.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}
