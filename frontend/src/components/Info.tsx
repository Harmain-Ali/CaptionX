import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { spring } from "../lib/motion";
import { Icon } from "./Icon";

/** A small (i) button. Hover, focus or tap shows a spring-in tooltip that never clips and flips to fit. */
export function Info({ children, label = "More info" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number; below: boolean; ax: number } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const id = useId();
  const timer = useRef<number | undefined>(undefined);

  const show = useCallback(() => { window.clearTimeout(timer.current); setOpen(true); }, []);
  const hide = useCallback(() => { window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setOpen(false), 90); }, []);

  useLayoutEffect(() => {
    if (!open || !btn.current) return;
    const r = btn.current.getBoundingClientRect();
    const w = Math.min(280, window.innerWidth - 24);
    const h = tip.current?.offsetHeight ?? 80;
    const below = r.top < h + 20;
    const cx = r.left + r.width / 2;
    const x = Math.max(12, Math.min(cx - w / 2, window.innerWidth - w - 12));
    setPos({ x, y: below ? r.bottom + 10 : r.top - 10, below, ax: cx - x });
  }, [open, children]);

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const away = (e: PointerEvent) => { if (!btn.current?.contains(e.target as Node) && !tip.current?.contains(e.target as Node)) setOpen(false); };
    const close = () => setOpen(false);
    window.addEventListener("keydown", esc);
    window.addEventListener("pointerdown", away);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("keydown", esc); window.removeEventListener("pointerdown", away);
      window.removeEventListener("scroll", close, true); window.removeEventListener("resize", close);
    };
  }, [open]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <>
      <button ref={btn} type="button" className={`info${open ? " on" : ""}`} aria-label={label} aria-describedby={open ? id : undefined}
              aria-expanded={open}
              onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((o) => !o); }}>
        <Icon name="info" size={15} />
      </button>
      {createPortal(
        <AnimatePresence>
          {open && (
            <motion.div ref={tip} id={id} role="tooltip" className="tip" onMouseEnter={show} onMouseLeave={hide}
                        style={{ left: pos?.x ?? -9999, top: pos?.y ?? -9999, transformOrigin: `${pos?.ax ?? 20}px ${pos?.below ? "0%" : "100%"}`,
                                 translateY: pos?.below ? 0 : "-100%", visibility: pos ? "visible" : "hidden" }}
                        initial={{ opacity: 0, scale: 0.88, y: pos?.below ? -6 : 6 }}
                        animate={{ opacity: 1, scale: 1, y: 0, transition: spring.bouncy }}
                        exit={{ opacity: 0, scale: 0.94, transition: { duration: 0.1 } }}>
              {children}
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}
