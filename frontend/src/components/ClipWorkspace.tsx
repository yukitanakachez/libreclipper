import { useEffect, useState } from "react";
import { api } from "../api";
import { notifyChanged } from "../changes";
import { OFFLINE, stateLabel } from "../labels";
import { useJob } from "../useJob";
import useShortcuts from "../useShortcuts";
import CandidateEditor, { type Trim } from "./CandidateEditor";
import ClipActions from "./ClipActions";
import ErrorPage from "./ErrorPage";
import Icon from "./Icon";
import JobStatus from "./JobStatus";
import MomentList, { momentLength } from "./MomentList";
import PhonePlayer, { type PhoneView } from "./PhonePlayer";
import Problem from "./Problem";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** The workspace's shape while the job first loads. */
function Skeleton() {
  return (
    <div className="ws-frame" aria-busy="true">
      <div className="workspace" tabIndex={-1}>
        <span className="skeleton sk-phone" />
        <div className="detail">
          <span className="visually-hidden">Loading the clip job</span>
          <span className="skeleton sk-title" />
          <span className="skeleton sk-meta" />
        </div>
      </div>
    </div>
  );
}

/**
 * A clip job: its moments in the list column (MomentList), the source or the rendered clip in
 * the phone, and the selected moment's details with its own Render button. It fills both cells
 * of `.main`, so the selected moment lives here and nowhere else.
 */
export default function ClipWorkspace({ jobId }: { jobId: string }) {
  const { job, error, offline, reload } = useJob(jobId,
    (j) => j.candidates.some((c) => c.render_pending || c.reframe_pending));
  const [selected, setSelected] = useState<number | null>(null);
  const [phone, setPhone] = useState<PhoneView>("source");
  const [actionError, setActionError] = useState<string | null>(null);
  // Each moment's trims this session (for ⌘Z / Undo), kept while you look at other moments.
  const [trims] = useState(() => new Map<string, Trim[]>());
  const trimsOf = (key: string) => {
    if (!trims.has(key)) trims.set(key, []);
    return trims.get(key)!;
  };

  const current = job ? job.candidates.find((c) => c.n === selected) ?? null : null;
  const clip = current?.clip ? job?.clips.find((k) => k.file === current.clip) ?? null : null;
  // The moment's render just finished: show it. (React's "adjust state on change" pattern.)
  const pendingKey = current ? `${current.n}:${current.render_pending}` : null;
  const [lastPending, setLastPending] = useState(pendingKey);
  if (pendingKey !== lastPending) {
    setLastPending(pendingKey);
    if (current && lastPending === `${current.n}:true` && !current.render_pending && current.clip) setPhone("rendered");
  }

  const canRender = !!job && !!current && job.editable && !current.render_pending && !current.reframe_pending;
  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); notifyChanged(); } catch (e) { setActionError((e as Error).message); }
  };
  const doRender = () => {
    if (!canRender || !current) return;
    setPhone("source");
    act(() => api.render(jobId, current.n));
  };
  useShortcuts({ "mod+enter": doRender });

  useEffect(() => {
    if (job) setSelected((s) => (s !== null && job.candidates.some((c) => c.n === s) ? s : job.candidates[0]?.n ?? null));
  }, [job]);

  const list = (
    <MomentList job={job} selected={selected} loading={!job && !error}
                onSelect={(n) => { setSelected(n); setPhone("source"); }} />
  );
  if (error) {
    const missing = /^No job called/.test(error);
    return <>{list}<ErrorPage title={missing ? "This job isn't here" : "Couldn't open this job"}
      message={missing ? "It may have been deleted, or the link is wrong." : error}
      onRetry={missing ? undefined : reload} /></>;
  }
  if (!job) {
    if (offline) return <>{list}<ErrorPage title="Can't reach Clipper" message="Failed to fetch" onRetry={reload} /></>;
    return <>{list}<Skeleton /></>;
  }

  const pickAgain = () => {
    const risky = job.candidates.some((c) => c.edited);
    const rendered = job.clips.length > 0 ? " Clips you already rendered stay on the Rendered page." : "";
    if (risky && !window.confirm(`Picking again replaces every moment, including your edits.${rendered} Continue?`)) return;
    act(() => api.repick(jobId, risky));
  };
  const working = !job.editable && job.status.state !== "failed";
  const episode = job.meta?.title ?? job.id;

  return (
    <>
      {list}
      <div className="workspace" tabIndex={-1}>
        <PhonePlayer jobId={jobId} candidate={current} clip={clip} view={phone} onView={setPhone} />
        <div className="detail">
          <div className="ws-head">
            <div>
              <h2>{current?.headline ?? episode}</h2>
              {current && (
                <p className="muted">
                  {episode} · {clock(current.start)} → {clock(current.end)} · {momentLength(current).toFixed(1)} s
                </p>
              )}
            </div>
            <button type="button" className="ghost" disabled={job.busy} onClick={pickAgain}
                    title="Ask Claude for a fresh set of moments"><Icon name="retry" />Pick again…</button>
          </div>
          {offline && <p className="offline">{OFFLINE}</p>}
          {job.status.state === "failed" && <JobStatus job={job} onRetried={notifyChanged} />}
          {working && <p className="muted">Busy: {stateLabel(job.status.state)}…</p>}
          {current && (
            <>
              <div className="actions">
                <button type="button" className="primary" disabled={!canRender} onClick={doRender}
                        aria-keyshortcuts="Meta+Enter" title="Render this clip (⌘↵)">
                  <Icon name="film" />{clip ? "Render again" : "Render"} <span className="kbd" aria-hidden="true">⌘↵</span>
                </button>
                {current.render_pending && (
                  <span className="rendering" role="status">
                    <span className="progress indeterminate" aria-hidden="true"><i /></span>Rendering…
                  </span>
                )}
                {current.reframe_pending && <span className="muted">Updating framing…</span>}
              </div>
              {current.reframe_error && <Problem message={`Couldn't update the framing: ${current.reframe_error}`} />}
              {current.render_error && !current.render_pending && <Problem message={current.render_error} />}
              {clip && !current.render_pending && <ClipActions jobId={jobId} clip={clip} />}
            </>
          )}
          {actionError && <Problem message={actionError} onDismiss={() => setActionError(null)} />}
          {job.candidates.length === 0 && ["ready_for_review", "done"].includes(job.status.state) && (
            <p className="muted">No moments were picked from this video. Check that it has speech, or use Pick again.</p>
          )}
          {current && <CandidateEditor key={`${current.n}:${current.orig_start}`} jobId={jobId}
            job={job} candidate={current} onChanged={reload}
            history={trimsOf(`${current.n}:${current.orig_start}`)} />}
        </div>
      </div>
    </>
  );
}
