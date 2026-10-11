/** A tiny pub/sub for the one polite live region (`Announcer`). Any part of the app calls
 *  `announce(text)`; the mounted `<Announcer/>` is the (usually only) subscriber that shows it. */
type Listener = (text: string) => void;

const listeners = new Set<Listener>();

export function announce(text: string): void {
  listeners.forEach((listener) => listener(text));
}

export function onAnnounce(listener: Listener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
