/** Tells the local server this page is open, so the packaged app can quit when its window is closed. */
const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
const body = () => JSON.stringify({ id });

function ping() {
  fetch("/api/presence/ping", { method: "POST", body: body(), keepalive: true }).catch(() => {});
}
function bye() {
  try {
    navigator.sendBeacon("/api/presence/bye", new Blob([body()], { type: "application/json" }));
  } catch { /* nothing else to do while the page is closing */ }
}

export function startPresence() {
  ping();
  window.setInterval(ping, 4000);
  window.addEventListener("pagehide", bye);
  window.addEventListener("pageshow", (e) => { if (e.persisted) ping(); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") ping(); });
}
