import { LayoutGroup, AnimatePresence, MotionConfig, motion } from "motion/react";
import { HealthProvider, useHealth } from "./lib/health";
import { href, useRoute } from "./lib/router";
import { CREATOR } from "./lib/links";
import { pageVariants, spring } from "./lib/motion";
import { ToastProvider } from "./components/Toast";
import { Icon } from "./components/Icon";
import { Logo, Wordmark } from "./components/Brand";
import { Studio } from "./pages/Studio";
import { History } from "./pages/History";
import { Settings } from "./pages/Settings";
import { Help } from "./pages/Help";

const NAV = [
  { name: "studio", label: "Studio", icon: "studio", to: href.studio },
  { name: "history", label: "History", icon: "history", to: href.history },
  { name: "settings", label: "Settings", icon: "settings", to: href.settings },
  { name: "help", label: "Help", icon: "help", to: href.help },
] as const;

function Status() {
  const { health, offline } = useHealth();
  const ready = !offline && !!health?.key_set && !!health?.ffmpeg;
  const text = offline ? "Backend offline" : !health ? "Connecting" : !health.key_set ? "Add your API key" : !health.ffmpeg ? "ffmpeg missing" : "Ready";
  const tone = offline ? "bad" : ready ? "ok" : !health ? "idle" : "warn";
  return (
    <a className={`status ${tone}`} href={ready || !health ? undefined : href.settings} title={text}>
      <i aria-hidden="true" /> {text}
    </a>
  );
}

function Credits() {
  return (
    <div className="credits">
      <p className="credits-line">Made by <a href={CREATOR.portfolio} target="_blank" rel="noopener noreferrer">{CREATOR.name}</a></p>
      <div className="socials">
        <a href={CREATOR.github} target="_blank" rel="noopener noreferrer" aria-label="GitHub" title="GitHub"><Icon name="github" size={18} /></a>
        <a href={CREATOR.linkedin} target="_blank" rel="noopener noreferrer" aria-label="LinkedIn" title="LinkedIn"><Icon name="linkedin" size={18} /></a>
        <a href={CREATOR.portfolio} target="_blank" rel="noopener noreferrer" aria-label="Portfolio" title="Portfolio"><Icon name="globe" size={18} /></a>
      </div>
    </div>
  );
}

function Shell() {
  const route = useRoute();
  const key = route.name + (route.name === "studio" ? (route.jobId ?? "") : "");

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <div className="app">
        <aside className="sidebar">
          <a className="brand" href={href.studio} aria-label="captionX, home">
            <Logo /> <Wordmark />
          </a>
          <LayoutGroup id="nav">
            <nav aria-label="Main" className="nav">
              {NAV.map((n) => {
                const on = route.name === n.name;
                return (
                  <a key={n.name} href={n.to} aria-current={on ? "page" : undefined}>
                    {on && <motion.span layoutId="nav-pill" className="nav-pill" transition={spring.snappy} />}
                    <Icon name={n.icon} size={19} />
                    <span>{n.label}</span>
                  </a>
                );
              })}
            </nav>
          </LayoutGroup>
          <div className="sidebar-foot">
            <Status />
            <Credits />
          </div>
        </aside>

        <div className="mobile-top"><a className="brand" href={href.studio}><Logo size={28} /> <Wordmark /></a><Status /></div>

        <main id="main" className="content">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={key} className="page" variants={pageVariants} initial="initial" animate="animate" exit="exit">
              {route.name === "studio" && <Studio jobId={route.jobId} />}
              {route.name === "history" && <History />}
              {route.name === "settings" && <Settings />}
              {route.name === "help" && <Help />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ToastProvider>
        <HealthProvider>
          <Shell />
        </HealthProvider>
      </ToastProvider>
    </MotionConfig>
  );
}
