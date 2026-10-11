import { useCallback } from "react";
import { api } from "./api";
import { isWorking, type JobDetail } from "./types";
import { usePolled } from "./usePolled";

/**
 * Loads a job and keeps it fresh (see usePolled: a failed refresh keeps the last good data on
 * screen and retries, so restarting the server never blanks the page). Polls while the job is
 * working, or while `busyWhen` says something else about it is.
 */
export function useJob(jobId: string, busyWhen?: (job: JobDetail) => boolean) {
  const load = useCallback(() => api.getJob(jobId), [jobId]);
  const { data: job, error, offline, reload } = usePolled(load,
    (j) => j.busy || isWorking(j.status.state) || !!busyWhen?.(j));
  return { job, error, offline, reload };
}
