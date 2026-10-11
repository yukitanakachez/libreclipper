import { explain } from "./components/Problem";
import { plural } from "./labels";
import type { ListItem } from "./listItems";
import { href } from "./route";

export type NotificationKind = "failed" | "review" | "rendered";

/** One thing that happened. `key` is stable, so read state survives polls and reloads: a
 *  failure carries its updated_at (a new failure is unread again), while "ready for review"
 *  and "rendered" show once per job (the user's own edits rewrite updated_at, and shouldn't
 *  relight them). */
export interface Notification {
  key: string; kind: NotificationKind;
  lead: string;                    // bold: "Rendered:", "Picking failed:"
  text: string;                    // what it's about: a title
  sub: string | null;              // a grey line under it
  href: string;
}

/** Steps as a person would say them: "Picking failed", not "pick failed". */
const STEP_NAME: Record<string, string> = {
  fetch: "Download", transcribe: "Transcription", pick: "Picking", reframe: "Framing",
  render: "Rendering",
};
const stepName = (step: string | null) =>
  step ? STEP_NAME[step] ?? step.charAt(0).toUpperCase() + step.slice(1) : "Job";

const ORDER: NotificationKind[] = ["failed", "review", "rendered"];

function fromItem(i: ListItem): Notification | null {
  const link = href({ id: i.id });
  if (i.state === "failed") {
    return { key: `failed:${i.id}:${i.updated_at ?? ""}`, kind: "failed", lead: `${stepName(i.failed_step)} failed:`,
             text: i.title, sub: i.error ? explain(i.error).text : null, href: link };
  }
  if (i.state === "ready_for_review") {
    return { key: `review:${i.id}`, kind: "review", lead: "Ready for review:", text: i.title, sub: null, href: link };
  }
  if (i.state === "done") {
    return { key: `rendered:${i.id}`, kind: "rendered", lead: "Rendered:", text: i.title,
             sub: plural(i.clips, "clip"), href: link };
  }
  return null;
}

/** The Inbox's notifications, most urgent kind first. */
export function buildNotifications(clips: ListItem[]): Notification[] {
  const notes = clips.map(fromItem).filter((n): n is Notification => n !== null);
  return notes.sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
}

const READ_KEY = "clipper.inbox.read";
const KEEP = 500;                  // read keys kept, newest last

/** The keys already read. Missing, junk or blocked storage means nothing is read. */
export function loadRead(): string[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(READ_KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((k): k is string => typeof k === "string") : [];
  } catch {
    return [];
  }
}

export function saveRead(keys: string[]): void {
  try {
    localStorage.setItem(READ_KEY, JSON.stringify(keys.slice(-KEEP)));
  } catch { /* storage blocked: read state lasts this session only */ }
}
