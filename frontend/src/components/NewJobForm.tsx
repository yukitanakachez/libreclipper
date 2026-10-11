import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { CampaignListing } from "../types";
import Icon from "./Icon";
import Problem from "./Problem";

/** "/Users/sam/Movies/Episode 12.mov" → "Episode 12.mov" */
const fileName = (path: string) => path.split(/[\\/]/).pop() || path;

export default function NewJobForm({ onCreated }: { onCreated: (id: string, existing: boolean) => void }) {
  const [campaigns, setCampaigns] = useState<CampaignListing[]>([]);
  const [source, setSource] = useState("");               // the chosen video's path on this computer
  const [campaign, setCampaign] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);                // a file is being dragged over the drop area
  const [copying, setCopying] = useState<{ name: string; done: number } | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listCampaigns().then((list) => {
      setCampaigns(list);
      const first = list.find((c) => c.valid);
      if (first) setCampaign((current) => current || first.slug);
    }).catch((e: Error) => setError(e.message));
  }, []);

  /** Click: the computer's own file chooser, which knows where the file is, so nothing is
   *  copied. Where the server can't open one (not a Mac), the browser's chooser instead. */
  async function choose() {
    setError(null);
    try {
      const { path } = await api.chooseFile();
      if (path) setSource(path);
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) picker.current?.click();
      else setError((err as Error).message);
    }
  }

  /** A dropped file comes without its location, so Clipper keeps its own copy to work from. */
  async function take(file: File | undefined) {
    if (!file) return;
    setError(null);
    setSource("");
    setCopying({ name: file.name, done: 0 });
    try {
      const { path } = await api.uploadVideo(file, (done) => setCopying({ name: file.name, done }));
      setSource(path);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCopying(null);
    }
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    if (!copying) void take(e.dataTransfer.files[0]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { id, existing } = await api.createJob(source, campaign);
      setSource("");
      onCreated(id, existing);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const percent = copying ? Math.round(copying.done * 100) : 0;
  return (
    <form className="new-job" onSubmit={submit}>
      <button type="button" className={`dropzone ${over ? "over" : ""} ${source ? "chosen" : ""}`}
              disabled={!!copying} onClick={choose}
              aria-label={source ? `Video file: ${fileName(source)}. Choose a different one`
                : "Video file: drop a video here, or click to choose one"}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }}
              onDragLeave={() => setOver(false)} onDrop={drop}>
        <Icon name={source ? "film" : "upload"} />
        {copying ? (
          <>
            <strong>Copying {copying.name}… {percent}%</strong>
            <span className="progress" aria-hidden="true"><i style={{ width: `${percent}%` }} /></span>
          </>
        ) : source ? (
          <>
            <strong title={source}>{fileName(source)}</strong>
            <span className="muted">Drop another video, or click to choose a different one</span>
          </>
        ) : (
          <>
            <strong>Drop a video here</strong>
            <span className="muted">or click to choose one from your computer</span>
          </>
        )}
      </button>
      <input ref={picker} type="file" accept="video/*" hidden tabIndex={-1} aria-hidden="true"
             onChange={(e) => { void take(e.target.files?.[0]); e.target.value = ""; }} />
      <label>Campaign
        <select value={campaign} onChange={(e) => setCampaign(e.target.value)} required>
          {campaigns.map((c) => (
            <option key={c.slug} value={c.slug} disabled={!c.valid}>
              {c.valid ? c.name : `${c.slug} — ${c.error}`}
            </option>
          ))}
        </select>
      </label>
      <button className="primary" disabled={busy || !!copying || !source || !campaign}>Start</button>
      {error && <Problem message={error} onDismiss={() => setError(null)} />}
    </form>
  );
}
