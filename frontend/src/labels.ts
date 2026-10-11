const LABELS: Record<string, string> = {
  queued: "Queued", fetching: "Downloading", transcribing: "Transcribing",
  picking: "Picking moments", reframing: "Framing", ready_for_review: "Ready for review",
  rendering: "Rendering", done: "Done", failed: "Failed",
};

export const stateLabel = (state: string): string => LABELS[state] ?? state;

/** What every list and page says while the server can't be reached. */
export const OFFLINE = "Can't reach Clipper. Retrying…";

/** "1 clip", "3 clips". */
export const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

export function formatSeconds(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
}

export function elapsed(sinceIso: string, nowMs: number): string {
  const total = Math.max(0, Math.floor((nowMs - Date.parse(sinceIso)) / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
