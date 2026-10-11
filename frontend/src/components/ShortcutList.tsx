type Row = { chips: string[]; label: string };

const ROWS: Row[] = [
  { chips: ["J", "K"], label: "Next / previous job or moment" },
  { chips: ["↵"], label: "Open (Next up)" },
  { chips: ["⌘↵"], label: "Render this clip" },
  { chips: ["⌘Z"], label: "Undo trim" },
  { chips: ["N"], label: "New" },
  { chips: ["Esc"], label: "Close a dialog" },
  { chips: ["?"], label: "This list" },
];

const TRANSCRIPT: Row[] = [
  { chips: ["Click", "↵"], label: "Start here" },
  { chips: ["⇧-click", "⇧↵"], label: "End here" },
  { chips: ["Double-click", "F2"], label: "Fix spelling" },
  { chips: ["←", "→"], label: "Move between words" },
];

function Rows({ rows, label }: { rows: Row[]; label?: string }) {
  return (
    <ul className="shortcut-list" aria-label={label}>
      {rows.map(({ chips, label }) => (
        <li key={label}>
          <span className="keys">
            {chips.map((chip, i) => (
              <span key={chip}>
                {i > 0 && <span className="muted"> / </span>}
                <span className="kbd">{chip}</span>
              </span>
            ))}
          </span>
          <span>{label}</span>
        </li>
      ))}
    </ul>
  );
}

/** The content of the "?" dialog: every shortcut, as .kbd chips, then the transcript's. */
export default function ShortcutList() {
  return (
    <>
      <Rows rows={ROWS} />
      <h3 className="shortcut-group">Transcript</h3>
      <Rows rows={TRANSCRIPT} label="Transcript" />
    </>
  );
}
