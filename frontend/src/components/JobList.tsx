import { useRef, useState } from "react";
import { api } from "../api";
import { notifyChanged } from "../changes";
import { elapsed, OFFLINE, stateLabel } from "../labels";
import { groupItems, itemStatus, type ListItem } from "../listItems";
import { href } from "../route";
import { isWorking } from "../types";
import type { JobListState } from "../useJobList";
import useShortcuts from "../useShortcuts";
import Icon from "./Icon";
import Orb from "./Orb";
import Problem from "./Problem";

function Row({ item, onRetry }: { item: ListItem; onRetry: (i: ListItem) => void }) {
  const working = isWorking(item.state);
  const detail = item.progress > 0 ? `${Math.round(item.progress * 100)}%`
    : working && item.updated_at ? elapsed(item.updated_at, Date.now()) : null;
  const status = `${detail ? `${stateLabel(item.state)} ${detail}` : itemStatus(item)} · ${item.subtitle}`;
  return (
    <div>
      <a className="row row-item" href={href({ id: item.id })}>
        <Orb id={item.id} size={44} />
        <div>
          <div className="row-title">{item.title}</div>
          <div className={`row-state ${item.state === "failed" ? "error" : "muted"}`}>{status}</div>
          {working && (
            <div className={`progress ${item.progress === 0 ? "indeterminate" : ""}`}>
              <i style={item.progress > 0 ? { width: `${Math.round(item.progress * 100)}%` } : undefined} />
            </div>
          )}
        </div>
      </a>
      {item.state === "failed" && (
        <div className="row">
          {item.error && <Problem message={item.error} persistent />}
          <button onClick={() => onRetry(item)}><Icon name="retry" />Retry from {item.failed_step ?? "the start"}</button>
        </div>
      )}
    </div>
  );
}

/** J and K walk the board's cards in the order they're on screen (Needs you, Working,
 *  Finished): they move focus, and ↵ on a focused card opens it, as on any link. */
function moveFocus(nav: HTMLElement | null, dir: 1 | -1) {
  const rows = Array.from(nav?.querySelectorAll<HTMLAnchorElement>("a.row-item") ?? []);
  if (rows.length === 0) return;
  const at = rows.indexOf(document.activeElement as HTMLAnchorElement);
  const next = at === -1 ? (dir === 1 ? 0 : rows.length - 1) : at + dir;
  rows[Math.min(rows.length - 1, Math.max(0, next))].focus();
}

/** Every clip job, grouped by what it is waiting for: a board of cards under Next up. */
export default function JobList({ jobs: { items, offline, loaded, error: loadError } }: { jobs: JobListState }) {
  const [error, setError] = useState<string | null>(null);
  const groups = groupItems(items);
  const navRef = useRef<HTMLElement>(null);

  useShortcuts({
    j: () => moveFocus(navRef.current, 1),
    k: () => moveFocus(navRef.current, -1),
  });

  async function retry(item: ListItem) {
    setError(null);
    try {
      await api.retry(item.id);
      notifyChanged();
    } catch (e) { setError((e as Error).message); }
  }

  const section = (title: string, list: ListItem[]) => list.length > 0 && (
    <section key={title}>
      <div className="sec">{title}<span>{list.length}</span></div>
      <div className="rows">{list.map((i) => <Row key={i.id} item={i} onRetry={retry} />)}</div>
    </section>
  );

  return (
    <nav ref={navRef} className="board" aria-label="Clip jobs">
      {offline && <p className="offline">{OFFLINE}</p>}
      {error && <Problem message={error} />}
      {!loaded ? (
        loadError ? <Problem message={loadError} /> : (
          <>
            <div className="skeleton" style={{ height: 44, margin: "0 8px 4px" }} />
            <div className="skeleton" style={{ height: 44, margin: "0 8px 4px" }} />
            <div className="skeleton" style={{ height: 44, margin: "0 8px 4px" }} />
          </>
        )
      ) : (
        <>
          {section("Needs you", groups.needs)}
          {section("Working", groups.working)}
          {section("Finished", groups.ready)}
        </>
      )}
    </nav>
  );
}
