import { plural, stateLabel } from "./labels";
import { isWorking, type JobSummary } from "./types";

export interface ListItem {
  id: string; title: string; subtitle: string; state: string;
  failed_step: string | null; error: string | null; updated_at: string | null;
  progress: number; busy: boolean;
  candidates: number;               // how many moments were picked
  clips: number;                    // how many clips are rendered
  posted: number;                   // how many of those are marked posted
}

export function fromJob(j: JobSummary): ListItem {
  return { id: j.id, title: j.title ?? j.source ?? j.id,
           subtitle: `${j.campaign ?? "—"} · ${j.candidates} moments`, state: j.state,
           failed_step: j.failed_step, error: j.error, updated_at: j.updated_at,
           progress: j.progress, busy: j.busy, candidates: j.candidates, clips: j.clips, posted: j.posted };
}

/** The row's status word: a done row says how many clips it made and how many are posted,
 *  others their state. */
export function itemStatus(i: ListItem): string {
  if (i.state !== "done" || i.clips === 0) return stateLabel(i.state);
  const rendered = `${plural(i.clips, "clip")} rendered`;
  return i.posted === 0 ? rendered : i.posted === i.clips ? `${rendered} · all posted` : `${rendered} · ${i.posted} posted`;
}

export function groupItems(items: ListItem[]) {
  return {
    needs: items.filter((i) => i.state === "ready_for_review" || i.state === "failed"),
    working: items.filter((i) => isWorking(i.state)),
    ready: items.filter((i) => i.state === "done"),
  };
}

/** The item that has needed you the longest: the needs group, oldest `updated_at` first (nulls last). */
export function oldestNeeds(items: ListItem[]): ListItem | null {
  const needs = groupItems(items).needs;
  if (needs.length === 0) return null;
  return [...needs].sort((a, b) => {
    if (a.updated_at === null) return b.updated_at === null ? 0 : 1;
    if (b.updated_at === null) return -1;
    return Date.parse(a.updated_at) - Date.parse(b.updated_at);
  })[0];
}

/** Rendered clips nobody has marked posted yet, across these jobs. */
export const unposted = (items: ListItem[]): number => items.reduce((sum, i) => sum + i.clips - i.posted, 0);
