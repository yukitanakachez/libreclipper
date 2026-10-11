import type { ReactNode } from "react";

/** 24-unit line drawings, stroked in the text colour. */
const PATHS = {
  play: <path d="M7 5l12 7-12 7z" />,
  check: <path d="M5 12l5 5 9-10" />,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" />
    <path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></>,
  folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  external: <><path d="M14 4h6v6" /><path d="M20 4l-9 9" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></>,
  trash: <><path d="M4 7h16" /><path d="M9 7V4h6v3" /><path d="M6 7l1 13h10l1-13" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  upload: <><path d="M12 15V4" /><path d="M7 9l5-5 5 5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>,
  film: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M10 9l5 3-5 3z" /></>,
  retry: <><path d="M20 12a8 8 0 1 1-2.35-5.65L20 8.5" /><path d="M20 4v4.5h-4.5" /></>,
  undo: <><path d="M9 14L4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" /></>,
  back: <><path d="M19 12H5" /><path d="M11 6l-6 6 6 6" /></>,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  // The top bar and its Inbox.
  gear: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>,
  bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 8 3 8H3s3-1 3-8" /><path d="M10 20a2 2 0 0 0 4 0" /></>,
  alert: <><path d="M12 9v4M12 17h.01" />
    <path d="M10.3 3.9L2 18a2 2 0 0 0 1.7 3h16.6A2 2 0 0 0 22 18L13.7 3.9a2 2 0 0 0-3.4 0z" /></>,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

/** A 16 px line icon for a button. Decoration only: the button's text or aria-label names it. */
export default function Icon({ name }: { name: IconName }) {
  return (
    <svg className="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  );
}
