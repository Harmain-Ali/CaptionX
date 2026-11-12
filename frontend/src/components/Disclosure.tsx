import { useId, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { spring } from "../lib/motion";
import { Icon } from "./Icon";

/** Smooth expand/collapse. The body animates its real height with a spring. */
export function Disclosure({ head, children, defaultOpen = false, open: controlled, onToggle, className = "" }: {
  head: ReactNode; children: ReactNode; defaultOpen?: boolean; open?: boolean; onToggle?: (o: boolean) => void; className?: string;
}) {
  const [inner, setInner] = useState(defaultOpen);
  const open = controlled ?? inner;
  const id = useId();
  const toggle = () => { const n = !open; setInner(n); onToggle?.(n); };
  return (
    <div className={`disclosure ${open ? "is-open" : ""} ${className}`}>
      <button type="button" className="disclosure-head" onClick={toggle} aria-expanded={open} aria-controls={id}>
        <span className="disclosure-title">{head}</span>
        <Icon name="chevron" className={`chev${open ? " open" : ""}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div id={id} className="disclosure-body" style={{ overflow: "hidden" }}
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1, transition: { height: spring.smooth, opacity: { duration: 0.2 } } }}
                      exit={{ height: 0, opacity: 0, transition: { height: spring.snappy, opacity: { duration: 0.12 } } }}>
            <div className="disclosure-inner">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
