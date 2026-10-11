import { useEffect, useRef } from "react";

/** True on macOS (and iPadOS/iOS reporting as Mac); false everywhere else, including when
 *  `navigator` gives nothing useful (older jsdom, odd embeddings) — those fall back to "not
 *  Mac", which still lets ⌘-as-metaKey shortcuts fire in tests (see modPressed below). */
function isMac(): boolean {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  const platform = nav.userAgentData?.platform ?? nav.platform ?? "";
  return /mac/i.test(platform) || /mac/i.test(nav.userAgent ?? "");
}

/** `mod` is ⌘ on Mac, Ctrl elsewhere. metaKey always counts as `mod`, even off Mac, so a test
 *  (or a Mac keyboard plugged into another OS) that dispatches metaKey still works. */
function modPressed(e: KeyboardEvent): boolean {
  return e.metaKey || (!isMac() && e.ctrlKey);
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

const PLAIN_KEYS = new Set(["j", "k", "n", "enter"]);
const MOD_KEYS: Record<string, string> = { enter: "mod+enter", z: "mod+z" };

/** A control that Enter already acts on by itself (follow a link, press a button …). */
function activatesOnEnter(target: EventTarget | null): boolean {
  return target instanceof Element
    && target.closest("a[href], button, summary, [role='button'], [role='link'], [role='menuitem'], [role='tab'], [role='option'], [role='listbox'], [role='separator']") !== null;
}

/** Maps a keydown to one of our shortcut names ("j" … "enter", "mod+enter" …), or null when it
 *  isn't one — including when it's aimed at an editable field, a dialog is open, or it carries
 *  modifiers the shortcut doesn't call for. Shift is allowed only for "?" (that's how it's
 *  typed on a US keyboard); every other plain key rejects it. A plain Enter on a link, button
 *  or other control is left to that control. */
function shortcutFor(e: KeyboardEvent): string | null {
  if (isEditableTarget(e.target)) return null;
  if (document.querySelector("dialog[open]")) return null;

  if (e.key === "?") {
    return e.ctrlKey || e.metaKey || e.altKey ? null : "?";
  }

  const key = e.key.toLowerCase();
  if (PLAIN_KEYS.has(key) && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
    return key === "enter" && activatesOnEnter(e.target) ? null : key;
  }

  const modName = MOD_KEYS[key];
  if (modName) {
    return modPressed(e) && !e.altKey && !e.shiftKey ? modName : null;
  }

  return null;
}

/** Wires the shared keyboard shortcuts to `map`, e.g. {j: goNext, "mod+enter": render}.
 *  Ignored while focus is in an input/textarea/select/contenteditable, while a dialog is open,
 *  with unexpected modifiers, and whenever `enabled` is false. Registers once per mount; the
 *  latest `map`/`enabled` are read through a ref, so callers can pass fresh closures every
 *  render without re-subscribing. */
export default function useShortcuts(map: Record<string, () => void>, enabled = true): void {
  const mapRef = useRef(map);
  mapRef.current = map;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!enabledRef.current) return;
      const name = shortcutFor(e);
      if (!name) return;
      const handler = mapRef.current[name];
      if (!handler) return;
      e.preventDefault();
      handler();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}
