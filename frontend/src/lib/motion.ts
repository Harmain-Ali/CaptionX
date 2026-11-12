import type { Transition } from "motion/react";

/** Real spring physics (stiffness, damping, mass) instead of fixed-duration easing. */
export const spring = {
  /** quick and tight: press feedback, pills, toggles */
  snappy: { type: "spring", stiffness: 520, damping: 38, mass: 0.7 } satisfies Transition,
  /** the default for things that move: pages, panels, lists */
  smooth: { type: "spring", stiffness: 300, damping: 30, mass: 0.9 } satisfies Transition,
  /** a little overshoot: tooltips, toasts, things that arrive */
  bouncy: { type: "spring", stiffness: 420, damping: 24, mass: 0.8 } satisfies Transition,
};

export const pageVariants = {
  initial: { opacity: 0, y: 14, scale: 0.995 },
  animate: { opacity: 1, y: 0, scale: 1, transition: spring.smooth },
  exit: { opacity: 0, y: -6, transition: { duration: 0.12, ease: "easeIn" as const } },
};

export const listVariants = {
  animate: { transition: { staggerChildren: 0.045, delayChildren: 0.04 } },
};
export const itemVariants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: spring.smooth },
};
