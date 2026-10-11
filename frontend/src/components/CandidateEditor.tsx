import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { announce } from "../announce";
import { formatSeconds } from "../labels";
import { endFromWord, nudge, NUDGE, startFromWord } from "../trim";
import type { CandidatePatch, CandidateView, JobDetail, Layout } from "../types";
import useShortcuts from "../useShortcuts";
import Icon from "./Icon";
import Problem from "./Problem";
import TranscriptWords from "./TranscriptWords";

const LAYOUT_LABEL: Record<Layout, string> = { auto: "Auto layout", stack: "Stack", fit: "Fit" };
const UNDO_SHOWN_MS = 10_000;
const NOT_AN_ACTION = new Set(["Meta", "Control", "Shift", "Alt", "Tab"]);   // keys that keep Undo shown

/** A moment's range before a trim, for undo. */
export type Trim = { start: number; end: number };

/** The trim line, the transcript and the folded headline/caption/layout/music of one moment.
 *  `history` holds this session's trims of the moment (the range before each), so ⌘Z and the
 *  Undo button can walk them back; the workspace keeps it across switching moments. */
export default function CandidateEditor({ jobId, job, candidate: c, onChanged, history: kept }: {
  jobId: string; job: JobDetail; candidate: CandidateView; onChanged: () => void; history?: Trim[];
}) {
  const [error, setError] = useState<string | null>(null);
  const [headline, setHeadline] = useState(c.headline);
  const [caption, setCaption] = useState(c.post_caption);
  const locked = !job.editable || c.render_pending;   // the server says 409 meanwhile
  const trimLocked = locked || c.reframe_pending;     // the server says 409 meanwhile
  const { min_start: lo, max_end: hi } = c.bounds;

  // Saves run one after another, so an undo can never overtake the trim it undoes.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const beforePick = useRef<Trim | null>(null);
  const [own] = useState<Trim[]>(() => []);
  const history = kept ?? own;
  // The range as of the last trim or undo, ahead of the reload that brings it back as props,
  // so quick trims record (and compute from) where the moment really is.
  const known = useRef<Trim>({ start: c.start, end: c.end });
  const saving = useRef(0);
  useEffect(() => {
    if (saving.current === 0) known.current = { start: c.start, end: c.end };
  }, [c.start, c.end]);
  // The Undo button shows after a trim, until the next action or UNDO_SHOWN_MS. Every trim
  // takes a new number from `shows`, so it restarts the timer even straight after a hide.
  const [undoShown, setUndoShown] = useState(0);         // 0: hidden
  const shows = useRef(0);
  const undoButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!undoShown) return;
    const hide = () => setUndoShown(0);
    const timer = window.setTimeout(hide, UNDO_SHOWN_MS);
    // Capture phase: runs before the action itself, so a new trim shows it again.
    const onAction = (e: Event) => {
      if (e instanceof KeyboardEvent && NOT_AN_ACTION.has(e.key)) return;
      if (e.target instanceof Node && undoButton.current?.contains(e.target)) return;
      hide();
    };
    document.addEventListener("pointerdown", onAction, true);
    document.addEventListener("keydown", onAction, true);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("pointerdown", onAction, true);
      document.removeEventListener("keydown", onAction, true);
    };
  }, [undoShown]);

  function save(patch: CandidatePatch) {
    saving.current += 1;
    queue.current = queue.current.then(async () => {
      setError(null);
      try { await api.patchCandidate(jobId, c.n, patch); onChanged(); }
      catch (e) { setError((e as Error).message); }
      finally { saving.current -= 1; }
    });
    return queue.current;
  }
  const moveTo = (range: Trim) => { known.current = range; save(range); };
  const trim = (patch: Partial<Trim>) => {
    history.push(known.current);
    known.current = { ...known.current, ...patch };
    shows.current += 1;
    setUndoShown(shows.current);
    save(patch);
  };
  const pick = (patch: Partial<Trim>) => {
    beforePick.current = known.current;
    trim(patch);
  };
  const undo = () => {
    const previous = history.pop();
    setUndoShown(0);
    if (!previous) return;
    moveTo(previous);
    announce("Trim undone");
  };
  useShortcuts({ "mod+z": () => { if (!trimLocked) undo(); } });

  const nudges = (edge: "Start" | "End") => (
    <span className="nudges">
      {([-NUDGE, NUDGE] as const).map((d) => {
        const label = `${d < 0 ? "−" : "+"}${NUDGE}`;
        return (
          <button key={d} type="button" disabled={trimLocked} aria-label={`${edge} ${label}`}
                  title={`${edge} ${Math.abs(d)} s ${d < 0 ? "earlier" : "later"}`}
                  onClick={() => {
                    const { start, end } = known.current;
                    trim(edge === "Start" ? { start: nudge(start, d, lo, end - 1) }
                      : { end: nudge(end, d, start + 1, hi) });
                  }}>{label}</button>
        );
      })}
    </span>
  );

  return (
    <section className="editor">
      <div className="trim">
        <span className="edge">Start <b>{formatSeconds(c.start)}</b>{nudges("Start")}</span>
        <span className="edge">End <b>{formatSeconds(c.end)}</b>{nudges("End")}</span>
        {undoShown > 0 && !trimLocked && (
          <button ref={undoButton} type="button" className="undo ghost" title="Undo trim (⌘Z)" onClick={undo}><Icon name="undo" />Undo</button>
        )}
      </div>
      {c.in_limits === false && job.campaign && (
        <p className="warn">That's outside this campaign's {job.campaign.min_len}–{job.campaign.max_len} s.</p>
      )}
      {!c.ends_on_sentence && <p className="muted">This clip doesn't end on a finished sentence.</p>}

      {/* A pick on the wrong side of the other edge still leaves at least a second of clip. */}
      <TranscriptWords words={c.words} start={c.start} end={c.end} disabled={trimLocked}
        onPickStart={(i) => pick({ start: startFromWord(c.words, i, { min_start: lo, max_end: known.current.end - 1 }) })}
        onPickEnd={(i) => pick({ end: endFromWord(c.words, i, { min_start: known.current.start + 1, max_end: hi }) })}
        onUndoPick={() => {
          const previous = beforePick.current;
          beforePick.current = null;
          if (!previous) return;
          history.pop();                                   // the pick it undoes
          setUndoShown(0);
          moveTo(previous);
        }}
        onFix={async (w, text) => {
          try { await api.saveWordFixes(jobId, { [String(w.i)]: text }); onChanged(); }
          catch (e) { setError((e as Error).message); }
        }} />

      <details className="fold">
        <summary>Headline, caption, layout &amp; music
          <span className="muted">{LAYOUT_LABEL[c.layout] ?? c.layout}{c.music_on ? " · music" : ""}</span></summary>
        <div className="fold-body">
          <label>Headline
            <input value={headline} disabled={locked} maxLength={200}
              onChange={(e) => setHeadline(e.target.value)}
              onBlur={() => headline !== c.headline && save({ headline })} />
          </label>
          <label>Post caption
            <textarea value={caption} disabled={locked} maxLength={2200} rows={3}
              onChange={(e) => setCaption(e.target.value)}
              onBlur={() => caption !== c.post_caption && save({ post_caption: caption })} />
          </label>
          <label>Layout
            <select value={c.layout} disabled={trimLocked} onChange={(e) => save({ layout: e.target.value as Layout })}>
              <option value="auto">Auto</option><option value="stack">Stack</option><option value="fit">Fit</option>
            </select>
          </label>
          {job.campaign?.music_allowed && (
            <div className="music">
              <label><input type="checkbox" checked={c.music_on} disabled={locked}
                onChange={(e) => save({ music_on: e.target.checked })} /> Music</label>
              {c.music_on && (
                <select value={c.music_track ?? ""} disabled={locked} aria-label="Music track"
                  onChange={(e) => save({ music_track: e.target.value || null })}>
                  <option value="">First track in the folder</option>
                  {job.campaign.tracks.map((t) => <option key={t} value={t}>{t.split("/").pop()}</option>)}
                </select>
              )}
            </div>
          )}
        </div>
      </details>
      {error && <Problem message={error} onDismiss={() => setError(null)} />}
    </section>
  );
}
