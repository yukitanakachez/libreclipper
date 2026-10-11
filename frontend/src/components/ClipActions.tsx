import { useState } from "react";
import { api } from "../api";
import { notifyChanged } from "../changes";
import type { Clip } from "../types";
import Icon from "./Icon";

/** What you do with a rendered clip: say it's posted (or take that back), copy its caption,
 *  find the file. The same row under a moment and on every card of the Rendered page. */
export default function ClipActions({ jobId, clip }: { jobId: string; clip: Clip }) {
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const posted = clip.posted_at !== null;

  const act = async (fn: () => Promise<unknown>, done?: string) => {
    setNote(null);
    try { await fn(); if (done) setNote({ ok: true, text: done }); }
    catch (e) { setNote({ ok: false, text: (e as Error).message }); }
  };
  async function copy() {
    try { await navigator.clipboard.writeText(clip.caption); setNote({ ok: true, text: "Copied caption + hashtags" }); }
    catch { setNote({ ok: false, text: "Couldn't copy: the text is in the .txt file next to the video." }); }
  }

  return (
    <div className="clip-actions">
      <div className="actions">
        <button type="button" className={`toggle ${posted ? "on" : ""}`} aria-pressed={posted}
                title={posted ? "Posted: press to mark it not posted" : "Mark this clip as posted"}
                onClick={() => act(async () => { await api.setPosted(jobId, clip.file, !posted); notifyChanged(); })}>
          <Icon name="check" />{posted ? "Posted" : "Mark posted"}</button>
        <button type="button" className="soft" onClick={copy}><Icon name="copy" />Copy caption</button>
        <button type="button" className="soft" onClick={() => act(() => api.reveal(jobId, clip.file))}>
          <Icon name="folder" />Show in Finder</button>
      </div>
      {note && <p className={note.ok ? "muted" : "error"} role="status">{note.text}</p>}
    </div>
  );
}
