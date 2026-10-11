import { useState } from "react";
import { loadRead, saveRead, type Notification, type NotificationKind } from "../inbox";
import Icon, { type IconName } from "./Icon";
import Popover from "./Popover";

const ICON: Record<NotificationKind, IconName> = {
  failed: "alert", review: "check", rendered: "film",
};

/** The bell: things that happened (jobs ready for review, renders done, failures). An orange
 *  dot while any is unread; read keys persist in localStorage (see inbox.ts). */
export default function Inbox({ notes }: { notes: Notification[] }) {
  const [read, setRead] = useState<string[]>(loadRead);
  const readSet = new Set(read);
  const unread = notes.filter((n) => !readSet.has(n.key));

  const markRead = (keys: string[]) => {
    const next = [...read.filter((k) => !keys.includes(k)), ...keys];
    setRead(next);
    saveRead(next);
  };

  return (
    <Popover label="Inbox" buttonLabel={unread.length > 0 ? `Inbox, ${unread.length} unread` : "Inbox"}
             trigger={<><Icon name="bell" />{unread.length > 0 && <span className="pip" aria-hidden="true" />}</>}>
      {(close) => (
        <>
          <div className="pop-head">
            <h2>Inbox</h2>
            {unread.length > 0 && (
              <button type="button" className="ghost" onClick={() => markRead(unread.map((n) => n.key))}>
                Mark all read</button>
            )}
          </div>
          {notes.length === 0 ? <p className="pop-empty muted">Nothing new</p> : (
            <ul className="notes">
              {notes.map((n) => (
                <li key={n.key}>
                  <a className={`note ${readSet.has(n.key) ? "" : "unread"}`} href={n.href}
                     onClick={() => { markRead([n.key]); close(); }}>
                    <span className="note-ic"><Icon name={ICON[n.kind]} /></span>
                    <span className="note-body">
                      <span><b>{n.lead}</b>{n.text && ` ${n.text}`}</span>
                      {n.sub && <> <small>{n.sub}</small></>}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Popover>
  );
}
