import { useState } from "react";
import { api, media } from "../api";
import { OFFLINE } from "../labels";
import { href } from "../route";
import type { RenderedClip } from "../types";
import { usePolled } from "../usePolled";
import ClipActions from "./ClipActions";
import Problem from "./Problem";

type Filter = "todo" | "posted" | "all";

// Module-level so usePolled doesn't see a new function (and reload) on every render.
const load = () => api.listClips();

/** "3 h ago", "2 d ago": how long since a clip was rendered or posted. */
function ago(iso: string): string {
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} h ago`;
  return `${Math.floor(minutes / (60 * 24))} d ago`;
}

/** "01-the-weekly-kill-list.mp4" → "The weekly kill list": for clips rendered before headlines were kept. */
function fromFile(file: string): string {
  const words = file.replace(/\.mp4$/, "").replace(/^\d+-/, "").replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function Card({ clip }: { clip: RenderedClip }) {
  const posted = clip.posted_at !== null;
  const title = clip.headline ?? fromFile(clip.file);
  return (
    <li className={`clip-card ${posted ? "posted" : ""}`}>
      <video src={media.clip(clip.job_id, clip.file, clip.version)} controls preload="metadata" />
      <div className="clip-what">
        <strong>{title}</strong>
        <a className="muted" href={href({ id: clip.job_id })}>{clip.job_title ?? clip.job_id}</a>
        <span className="muted">
          {posted ? <span className="ok">Posted {ago(clip.posted_at!)}</span> : "Not posted"} · rendered {ago(clip.rendered_at)}
        </span>
        <ClipActions jobId={clip.job_id} clip={clip} />
      </div>
    </li>
  );
}

/** Every rendered clip of every job, newest first: what's still to post, and what's out. */
export default function RenderedPage() {
  const { data, error, offline } = usePolled(load);
  const [filter, setFilter] = useState<Filter>("todo");
  const clips = data ?? [];
  const todo = clips.filter((c) => c.posted_at === null);
  const posted = clips.filter((c) => c.posted_at !== null);
  const shown = filter === "todo" ? todo : filter === "posted" ? posted : clips;

  const tab = (f: Filter, label: string, count: number) => (
    <button type="button" role="tab" aria-selected={filter === f} className={filter === f ? "on" : ""}
            onClick={() => setFilter(f)}>{label}<span>{count}</span></button>
  );

  return (
    <div className="rendered-page" tabIndex={-1}>
      <div className="rendered-head">
        <h2>Rendered clips</h2>
        <div className="filter" role="tablist" aria-label="Show">
          {tab("todo", "Not posted", todo.length)}
          {tab("posted", "Posted", posted.length)}
          {tab("all", "All", clips.length)}
        </div>
      </div>
      {offline && <p className="offline">{OFFLINE}</p>}
      {error && <Problem message={error} />}
      {data !== null && shown.length === 0 && (
        <p className="muted">
          {clips.length === 0 ? "Nothing rendered yet. Open a job, pick a moment and press Render."
            : filter === "todo" ? "Everything you rendered is posted." : "Nothing marked as posted yet."}
        </p>
      )}
      <ul className="clip-grid">
        {shown.map((c) => <Card key={`${c.job_id}/${c.file}`} clip={c} />)}
      </ul>
    </div>
  );
}
