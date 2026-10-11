import { useState } from "react";
import { api } from "../api";
import type { JobDetail } from "../types";
import Icon from "./Icon";
import Problem from "./Problem";

/** A failed job in its workspace: why it failed, and Retry from the step that did. */
export default function JobStatus({ job, onRetried }: { job: JobDetail; onRetried: () => void }) {
  const { error, failed_step } = job.status;
  const [retryError, setRetryError] = useState<string | null>(null);
  return (
    <div className="job-status">
      {error && <Problem message={error} />}
      <button onClick={async () => {
        setRetryError(null);
        try { await api.retry(job.id); onRetried(); }
        catch (e) { setRetryError((e as Error).message); }
      }}>
        <Icon name="retry" />Retry from {failed_step ?? "the start"}
      </button>
      {retryError && <Problem message={retryError} />}
    </div>
  );
}
