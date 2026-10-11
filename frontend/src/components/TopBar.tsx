import type { Notification } from "../inbox";
import { plural } from "../labels";
import { href } from "../route";
import Icon from "./Icon";
import Inbox from "./Inbox";

/** The slim bar over the board and workspace: Clipper (the way back to the board) and the open
 *  job on the left; the Rendered page, the Inbox, Settings, the shortcut list and New on the right. */
export default function TopBar({ title, notes, toPost, onRendered, onSettings, onNew, onHelp }: {
  title?: string; notes: Notification[]; toPost: number; onRendered: boolean; onSettings: boolean;
  onNew: () => void; onHelp: () => void;
}) {
  return (
    <header className="topbar">
      <p className="crumb">
        <a className="brand" href={href({ id: null })}><span className="logo" aria-hidden="true" />Clipper</a>
        {title && <><span className="crumb-sep" aria-hidden="true">/</span><b title={title}>{title}</b></>}
      </p>
      <div className="top-actions">
        <a className={`button ghost ${onRendered ? "on" : ""}`} href={href({ id: null, rendered: true })}
           aria-current={onRendered ? "page" : undefined}
           title={toPost > 0 ? `${plural(toPost, "rendered clip")} not posted yet` : "Every rendered clip"}>
          <Icon name="film" />Rendered{toPost > 0 && <span className="count">{toPost}</span>}
        </a>
        <Inbox notes={notes} />
        <a className={`button top-btn ${onSettings ? "on" : ""}`} href={href({ id: null, settings: true })}
           aria-label="Settings" title="Settings: AI provider and setup" aria-current={onSettings ? "page" : undefined}>
          <Icon name="gear" /></a>
        <button type="button" className="top-btn" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)"
                onClick={onHelp}><span aria-hidden="true">?</span></button>
        <button type="button" onClick={onNew}><Icon name="plus" />New <span className="kbd">N</span></button>
      </div>
    </header>
  );
}
