import { useEffect, useState } from "react";

export type Route =
  | { name: "studio"; jobId?: string }
  | { name: "history" }
  | { name: "settings" }
  | { name: "help" };

function parse(hash: string): Route {
  const h = hash.replace(/^#\/?/, "");
  if (h.startsWith("job/")) return { name: "studio", jobId: h.slice(4).split("/")[0] };
  if (h.startsWith("history")) return { name: "history" };
  if (h.startsWith("settings")) return { name: "settings" };
  if (h.startsWith("help")) return { name: "help" };
  return { name: "studio" };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (path: string) => { window.location.hash = path; };
export const href = {
  studio: "#/",
  job: (id: string) => `#/job/${id}`,
  history: "#/history",
  settings: "#/settings",
  help: "#/help",
};
