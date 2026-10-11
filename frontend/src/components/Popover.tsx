import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

const FOCUSABLE = 'a[href], button:not(:disabled), input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** A small panel anchored under a top-bar button. Not a modal: the page stays usable. The
 *  button says aria-expanded; opening moves focus to the panel's first control (else the
 *  panel), Esc closes and gives focus back to the button, and a click or focus outside closes it. */
export default function Popover({ label, buttonLabel, buttonClass = "", trigger, children }: {
  label: string; buttonLabel: string; buttonClass?: string; trigger: ReactNode;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    (panel.current?.querySelector<HTMLElement>(FOCUSABLE) ?? panel.current)?.focus();
    const away = (e: Event) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  const close = useCallback(() => { setOpen(false); button.current?.focus(); }, []);
  // `close` reads the button ref only when a note or button inside is clicked, never while
  // rendering; handing it to the panel's content is not a ref read (react/refs false positive).
  // oxlint-disable-next-line react/refs
  const content = open ? children(close) : null;
  const onKeyDown = (e: KeyboardEvent) => {
    if (open && e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  };

  return (
    <div className="pop-wrap" ref={wrap} onKeyDown={onKeyDown}
         onBlur={(e) => {
           // Tabbing out closes it; a blur with nowhere to go (Safari's clicks) is left to pointerdown.
           const next = e.relatedTarget as Node | null;
           if (open && next && !wrap.current?.contains(next)) setOpen(false);
         }}>
      <button ref={button} type="button" className={`top-btn ${buttonClass}`} aria-label={buttonLabel}
              title={label} aria-expanded={open} aria-controls={open ? id : undefined}
              onClick={() => (open ? close() : setOpen(true))}>
        {trigger}
      </button>
      {open && (
        <div ref={panel} id={id} className="popover" role="dialog" aria-label={label} tabIndex={-1}>
          {content}
        </div>
      )}
    </div>
  );
}
