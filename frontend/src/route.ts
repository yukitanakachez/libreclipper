import { useSyncExternalStore } from "react";

/** The board of every clip job (`id` null), one open job, the page of rendered clips,
 *  or Settings. */
export type Route = { id: string | null; rendered?: true; settings?: true };

export function parseHash(hash: string): Route {
  let parts: string[];
  try {
    parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return { id: null };           // a malformed link
  }
  if (parts[0] === "rendered" && parts.length === 1) return { id: null, rendered: true };
  if (parts[0] === "settings" && parts.length === 1) return { id: null, settings: true };
  // "#/jobs/<id>" is the older form of "#/clips/<id>".
  if ((parts[0] === "clips" || parts[0] === "jobs") && parts[1]
      && (parts.length === 2 || (parts.length === 3 && parts[2] === "output"))) {
    return { id: parts[1] };
  }
  return { id: null };
}

export function href(route: Route): string {
  if (route.rendered) return "#/rendered";
  if (route.settings) return "#/settings";
  return route.id ? `#/clips/${encodeURIComponent(route.id)}` : "#/";
}

const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return parseHash(hash);
}

export function go(route: Route): void {
  window.location.hash = href(route);
}
