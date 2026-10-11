import { stateLabel } from "../labels";
import { groupItems, itemStatus, oldestNeeds, unposted, type ListItem } from "../listItems";
import { go, href } from "../route";
import useShortcuts from "../useShortcuts";
import Icon from "./Icon";
import Orb from "./Orb";
import { HeroTexture } from "./Texture";

/** The top of the board when nothing is open: what needs you most, and how things stand. */
export default function NextUp({ jobs: { items, loaded }, onNew }: {
  jobs: { items: ListItem[]; loaded: boolean }; onNew: () => void;
}) {
  const groups = groupItems(items);
  const oldest = oldestNeeds(items);
  // ↵ opens the job named below, like its Open ↵ button; only while there is one to open.
  const openable = loaded ? oldest : null;
  useShortcuts({ enter: () => { if (openable) go({ id: openable.id }); } }, openable !== null);

  if (!loaded) {
    return (
      <div className="next-up" tabIndex={-1}>
        <div className="skeleton" style={{ height: 24, width: 160 }} />
        <div className="skeleton" style={{ height: 88 }} />
      </div>
    );
  }

  if (!oldest) {
    return (
      <div className="next-up caught-up" tabIndex={-1}>
        <HeroTexture />
        <h3>{items.length === 0 ? "Turn a video into clips" : "All caught up"}</h3>
        <button className="primary" onClick={onNew}><Icon name="plus" />New clip job</button>
      </div>
    );
  }

  const count = groups.needs.length;
  const moments = groups.needs.filter((i) => i.state === "ready_for_review")
    .reduce((sum, i) => sum + i.candidates, 0);
  const working = groups.working.length === 0
    ? "Nothing" : `${groups.working.length} · ${stateLabel(groups.working[0].state).toLowerCase()}`;

  return (
    <div className="next-up" tabIndex={-1}>
      <HeroTexture />
      <div className="next-card">
        <Orb id={oldest.id} size={44} />
        <div>
          <h3>Next up <span className="s">{count} {count === 1 ? "job needs" : "jobs need"} you.</span></h3>
          <div className="t">{oldest.title}</div>
          <div className="d">{itemStatus(oldest)} · {oldest.subtitle}</div>
        </div>
        <a className="button primary" href={href({ id: oldest.id })}>
          Open <span className="kbd">↵</span>
        </a>
      </div>
      <div className="tiles">
        <div className="tile"><div className="k">Working</div><div className="v">{working}</div></div>
        <div className="tile"><div className="k">Moments to review</div><div className="v">{moments}</div></div>
        <a className="tile" href={href({ id: null, rendered: true })}>
          <div className="k">Rendered, not posted</div><div className="v">{unposted(items)}</div>
        </a>
      </div>
    </div>
  );
}
