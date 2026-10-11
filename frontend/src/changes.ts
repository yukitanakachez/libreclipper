/** "Something changed": lets the list and the open workspace refresh each other. */
const listeners = new Set<() => void>();

export function notifyChanged(): void {
  listeners.forEach((listener) => listener());
}

export function onChanged(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
