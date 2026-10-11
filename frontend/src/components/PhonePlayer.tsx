import { useEffect, useId, useRef } from "react";
import { media } from "../api";
import type { CandidateView, Clip } from "../types";
import IPhoneFrame from "./IPhoneFrame";

export type PhoneView = "source" | "rendered";

/** The job's source video, letterboxed, seeking to the moment and stopping at its end. */
function SourceVideo({ jobId, candidate: c }: { jobId: string; candidate: CandidateView }) {
  const video = useRef<HTMLVideoElement>(null);
  const end = useRef(c.end);
  end.current = c.end;
  const armed = useRef(false);                    // pause at the end of this play-through
  const last = useRef<{ n: number; start: number } | null>(null);

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    const prev = last.current;
    last.current = { n: c.n, start: c.start };
    if (prev && prev.n === c.n && prev.start === c.start) return;
    v.currentTime = c.start;                      // opening, picking a moment, or a new start
    armed.current = true;
    // Picking another moment plays it; opening the job or trimming only moves the playhead.
    if (prev && prev.n !== c.n) void v.play().catch(() => {});
  }, [c.n, c.start]);

  return (
    <video ref={video} className="source" src={media.proxy(jobId)} controls preload="metadata"
      onPlay={(e) => {
        // Playing from inside the moment stops at its end again; from past it, it plays on.
        armed.current = e.currentTarget.currentTime < end.current - 0.05;
      }}
      onTimeUpdate={(e) => {
        const v = e.currentTarget;
        if (armed.current && v.currentTime >= end.current) {
          v.pause();
          armed.current = false;
        }
      }} />
  );
}

/**
 * The phone in the clip workspace: the source video at the selected moment, or the clip
 * rendered from it. Plain Source · Rendered toggles under the phone; Rendered is off until the
 * moment has a clip.
 */
export default function PhonePlayer({ jobId, candidate: c, clip, view, onView }: {
  jobId: string; candidate: CandidateView | null; clip: Clip | null; view: PhoneView;
  onView: (v: PhoneView) => void;
}) {
  const id = useId();
  const shown: PhoneView = view === "rendered" && clip ? "rendered" : "source";

  const toggle = (v: PhoneView, label: string, disabled: boolean) => (
    <button type="button" aria-pressed={shown === v} aria-controls={`${id}-screen`}
            aria-label={`Show ${label.toLowerCase()} in the phone`}
            className={shown === v ? "on" : ""} disabled={disabled}
            onClick={() => onView(v)}>{label}</button>
  );

  let screen;
  if (!c) screen = <p className="muted">No moment picked yet.</p>;
  else if (shown === "rendered" && clip) {
    screen = <video key={clip.version} className="rendered" src={media.clip(jobId, clip.file, clip.version)} controls />;
  } else screen = <SourceVideo jobId={jobId} candidate={c} />;

  return (
    <IPhoneFrame below={c && (
      <div className="phone-tabs" role="group" aria-label="Show in the phone">
        {toggle("source", "Source", false)}
        {toggle("rendered", "Rendered", !clip)}
      </div>
    )}>
      <div className="phone-panel" id={`${id}-screen`}>{screen}</div>
    </IPhoneFrame>
  );
}
