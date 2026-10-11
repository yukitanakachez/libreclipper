import { useEffect, useState } from "react";
import { onAnnounce } from "../announce";

/** One polite live region, mounted once in App. To re-announce identical text (the screen
 *  reader otherwise stays silent on a no-op change), it clears first and sets on the next tick. */
export default function Announcer() {
  const [text, setText] = useState("");

  useEffect(() => onAnnounce((next) => {
    setText("");
    setTimeout(() => setText(next), 0);
  }), []);

  return <div className="visually-hidden" aria-live="polite" role="status">{text}</div>;
}
