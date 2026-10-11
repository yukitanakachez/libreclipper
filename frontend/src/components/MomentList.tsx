import { useEffect, useRef } from "react";
import { plural } from "../labels";
import { href } from "../route";
import type { CandidateView, JobDetail } from "../types";
import useShortcuts from "../useShortcuts";
import Icon from "./Icon";

/** A moment's length: the paced (finished) length when known, else its range. */
export const momentLength = (c: CandidateView) => c.finished_length ?? c.end - c.start;

function Moment({ c, posted, selected, onSelect }: {
  c: CandidateView; posted: boolean; selected: boolean; onSelect: (n: number) => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);
  return (
    <button ref={ref} type="button" className={`row moment-row ${selected ? "sel" : ""} ${posted ? "posted" : ""}`}
            aria-current={selected || undefined} onClick={() => onSelect(c.n)}>
      <span>
        <span className="row-title">{c.headline}</span>
        <span className="row-state muted">
          {momentLength(c).toFixed(1)} s
          {c.render_pending ? <> · Rendering…</>
            : posted ? <> · <span className="ok posted-mark"><Icon name="check" />Posted</span></>
            : c.clip && <> · <span className="ok">Rendered</span></>}
          {c.needs_check && <> · <span className="warn">Check framing</span></>}
        </span>
      </span>
      <span className="score"><span className="visually-hidden">score </span>{c.score}</span>
    </button>
  );
}

/** The list column while a clip job is open: its moments, best first as picked. */
export default function MomentList({ job, selected, onSelect, loading = !job }: {
  job: JobDetail | null; selected: number | null; onSelect: (n: number) => void; loading?: boolean;
}) {
  const count = job?.candidates.length ?? 0;

  // J/K move to the next/previous moment in picked order; from nothing selected, J picks the
  // first (at === -1, so dir=1 lands on index 0).
  useShortcuts({
    j: () => moveSelection(1),
    k: () => moveSelection(-1),
  });

  function moveSelection(dir: 1 | -1) {
    const candidates = job?.candidates ?? [];
    if (candidates.length === 0) return;
    const at = candidates.findIndex((c) => c.n === selected);
    const next = at + dir;
    if (next < 0 || next >= candidates.length) return;
    onSelect(candidates[next].n);
  }
  return (
    <nav className="sidebar moment-list" aria-label="Moments">
      <a className="back" href={href({ id: null })}><Icon name="back" />All clip jobs</a>
      {job ? (
        <>
          <div className="sec">{plural(count, "moment")}</div>
          {job.candidates.map((c) => (
            <Moment key={c.n} c={c} selected={c.n === selected} onSelect={onSelect}
                    posted={!c.render_pending && job.clips.some((k) => k.file === c.clip && k.posted_at !== null)} />
          ))}
        </>
      ) : loading && (
        <div aria-hidden="true">
          <div className="skeleton" style={{ height: 44, margin: "8px 8px 4px" }} />
          <div className="skeleton" style={{ height: 44, margin: "0 8px 4px" }} />
        </div>
      )}
    </nav>
  );
}
