import { Fragment, useId, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import type { Word } from "../types";

const HINT = "Click: start here · ⇧-click: end here · double-click: fix spelling";

/**
 * The transcript as flowing text, one tab stop. Click a word: the clip starts there;
 * ⇧-click: it ends there. With the keyboard, ←/→ move a cursor, ↵ sets the start, ⇧↵ the
 * end, F2 fixes the spelling. Words inside the clip are `aria-selected`.
 *
 * A click trims at once. A double-click's first click has already trimmed by the time the
 * browser knows it was a double-click, however slow it was, so the double-click undoes that
 * trim (onUndoPick) and then opens the spelling box.
 */
export default function TranscriptWords(
  { words, start, end, disabled, onPickStart, onPickEnd, onUndoPick, onFix }: {
  words: Word[]; start: number; end: number; disabled: boolean;
  onPickStart: (index: number) => void; onPickEnd: (index: number) => void; onUndoPick: () => void;
  onFix: (word: Word, text: string) => void;
},
) {
  const id = useId();
  const box = useRef<HTMLDivElement>(null);
  const inside = (w: Word) => w.start >= start - 1e-6 && w.end <= end + 1e-6;
  const first = words.findIndex(inside);
  let last = -1;
  words.forEach((w, k) => { if (inside(w)) last = k; });
  const [cursor, setCursor] = useState(Math.max(0, first));
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const at = Math.min(cursor, words.length - 1);

  const edit = (k: number) => { setDraft(words[k].text); setEditing(k); };
  const moveTo = (k: number) => {
    setCursor(k);
    document.getElementById(`${id}-${k}`)?.scrollIntoView?.({ block: "nearest" });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget || disabled || words.length === 0) return;   // not the spelling box
    const keys: Record<string, () => void> = {
      ArrowRight: () => moveTo(Math.min(at + 1, words.length - 1)),
      ArrowLeft: () => moveTo(Math.max(at - 1, 0)),
      Home: () => moveTo(0),
      End: () => moveTo(words.length - 1),
      Enter: () => (e.shiftKey ? onPickEnd : onPickStart)(at),
      F2: () => edit(at),
    };
    const run = keys[e.key];
    if (!run) return;
    e.preventDefault();
    run();
  };

  const onWordClick = (e: MouseEvent, k: number) => {
    if (disabled) return;
    setCursor(k);
    if (e.detail > 1) return;                                // the 2nd click of a double
    (e.shiftKey ? onPickEnd : onPickStart)(k);
  };

  const close = () => { setEditing(null); box.current?.focus(); };

  return (
    <div ref={box} className={`transcript ${disabled ? "locked" : ""}`} role="listbox" aria-label="Transcript"
         aria-multiselectable="true" aria-disabled={disabled || undefined} tabIndex={0} title={HINT}
         aria-activedescendant={words.length > 0 && editing === null ? `${id}-${at}` : undefined}
         onKeyDown={onKeyDown}>
      {words.map((w, k) => {
        if (editing === k) {
          return (
            <input key={w.i} aria-label="Fix spelling" autoFocus value={draft} size={Math.max(4, draft.length + 1)}
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={() => setEditing(null)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && draft.trim()) { onFix(w, draft.trim()); close(); }
                if (e.key === "Escape") { e.stopPropagation(); close(); }
              }} />
          );
        }
        const on = k >= first && k <= last && first >= 0;
        const cls = ["w", on && "in", k === first && "start", k === last && "end", k === at && "cursor"]
          .filter(Boolean).join(" ");
        // Inside the clip the space between words is tinted too, so the range reads as one run.
        // Gaps are hidden from assistive tech: the listbox's children are its options.
        const space = k === words.length - 1 ? null
          : <span className={`w-gap ${on && k !== last ? "in" : ""}`} aria-hidden="true"> </span>;
        return (
          <Fragment key={w.i}>
            <span id={`${id}-${k}`} role="option" aria-selected={on} className={cls}
                  onClick={(e) => onWordClick(e, k)}
                  onDoubleClick={() => { if (disabled) return; onUndoPick(); edit(k); }}>
              {w.text}
            </span>
            {space}
          </Fragment>
        );
      })}
    </div>
  );
}
