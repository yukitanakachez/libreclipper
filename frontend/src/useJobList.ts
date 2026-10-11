import { api } from "./api";
import { fromJob, type ListItem } from "./listItems";
import { isWorking } from "./types";
import { usePolled } from "./usePolled";

// Module-level so usePolled doesn't see a new function (and reload) on every render.
const load = async (): Promise<ListItem[]> => (await api.listJobs()).map(fromJob);
const anyWorking = (items: ListItem[]) => items.some((i) => i.busy || isWorking(i.state));

export interface JobListState { items: ListItem[]; loaded: boolean; error: string | null; offline: boolean }

/** Every clip job, polled while any is working and reloaded when something changes
 *  (changes.ts). App loads it once, for the board, Next up, the Inbox and the top bar. */
export function useJobList(): JobListState {
  const { data, error, offline } = usePolled(load, anyWorking);
  return { items: data ?? [], loaded: data !== null, error, offline };
}
