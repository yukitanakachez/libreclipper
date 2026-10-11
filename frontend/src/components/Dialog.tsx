import { useEffect, useId, useRef, type ReactNode } from "react";

const FOCUSABLE = 'button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/** A native <dialog> opened with showModal(): focus moves in (to the first match of
 *  `initialFocus` if given, else the first focusable), Esc and a click on the dialog itself
 *  (its own box, or the ::backdrop in real browsers — both report the dialog as the click
 *  target) close it, and focus returns to whatever had it before opening. */
export default function Dialog({ title, onClose, initialFocus, children }: {
  title: string; onClose: () => void; initialFocus?: string; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; });
  const titleId = useId();
  const initialFocusRef = useRef(initialFocus);            // read once, on open

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialog.showModal();
    const first = initialFocusRef.current;
    const focusable = (first ? dialog.querySelector<HTMLElement>(first) : null)
      ?? dialog.querySelector<HTMLElement>(FOCUSABLE);
    (focusable ?? dialog).focus();

    let closing = false;
    const requestClose = () => {
      if (closing) return;
      closing = true;
      onCloseRef.current();
    };
    // Real browsers fire `cancel` (then `close`) on Escape; jsdom has neither, so we also
    // handle the keydown ourselves. `closing` keeps a real browser from calling onClose twice.
    const onCancel = (e: Event) => { e.preventDefault(); requestClose(); };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); requestClose(); }
    };
    const onClick = (e: MouseEvent) => { if (e.target === dialog) requestClose(); };
    dialog.addEventListener("cancel", onCancel);
    dialog.addEventListener("keydown", onKeyDown);
    dialog.addEventListener("click", onClick);

    return () => {
      dialog.removeEventListener("cancel", onCancel);
      dialog.removeEventListener("keydown", onKeyDown);
      dialog.removeEventListener("click", onClick);
      if (dialog.open) dialog.close();
      previouslyFocused?.focus();
    };
  }, []);

  return (
    <dialog ref={ref} className="sheet" tabIndex={-1} aria-labelledby={titleId}>
      {/* All visual chrome (padding, background, radius, shadow) lives on this wrapper, not
          on the <dialog> itself, so a click anywhere inside it — including its own padding
          and grid gap — lands on this element, not on the dialog. Only a genuine outside
          click (the dialog's own now-empty box, or ::backdrop in real browsers) has
          e.target === the dialog element, which is what closes it. */}
      <div className="dialog-body">
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </dialog>
  );
}
