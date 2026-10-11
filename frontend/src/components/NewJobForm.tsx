import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import type { CampaignListing } from "../types";
import Problem from "./Problem";

export default function NewJobForm({ onCreated }: { onCreated: (id: string, existing: boolean) => void }) {
  const [campaigns, setCampaigns] = useState<CampaignListing[]>([]);
  const [source, setSource] = useState("");
  const [campaign, setCampaign] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listCampaigns().then((list) => {
      setCampaigns(list);
      const first = list.find((c) => c.valid);
      if (first) setCampaign((current) => current || first.slug);
    }).catch((e: Error) => setError(e.message));
  }, []);

  async function choose() {
    setError(null);
    try {
      const { path } = await api.chooseFile();
      if (path) setSource(path);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { id, existing } = await api.createJob(source.trim(), campaign);
      setSource("");
      onCreated(id, existing);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="new-job" onSubmit={submit}>
      <label>YouTube link or file
        <input value={source} onChange={(e) => setSource(e.target.value)}
               placeholder="https://youtu.be/… or /path/to/episode.mp4" required />
      </label>
      <button type="button" onClick={choose}>Choose file…</button>
      <label>Campaign
        <select value={campaign} onChange={(e) => setCampaign(e.target.value)} required>
          {campaigns.map((c) => (
            <option key={c.slug} value={c.slug} disabled={!c.valid}>
              {c.valid ? c.name : `${c.slug} — ${c.error}`}
            </option>
          ))}
        </select>
      </label>
      <button className="primary" disabled={busy || !source.trim() || !campaign}>Start</button>
      {error && <Problem message={error} onDismiss={() => setError(null)} />}
    </form>
  );
}
