import type { Word } from "./types";

const PREROLL = 0.1;
const TAIL = 0.3;
const GUARD = 0.05;
export const NUDGE = 0.5;

type Bounds = { min_start: number; max_end: number };
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);
const round2 = (v: number) => Math.round(v * 100) / 100;

/** Start just before word i, never reaching into the previous word. */
export function startFromWord(words: Word[], i: number, bounds: Bounds): number {
  const w = words[i];
  let start = w.start - PREROLL;
  if (i > 0) start = Math.max(start, words[i - 1].end + GUARD);
  start = Math.min(start, w.start);
  return round2(clamp(start, bounds.min_start, bounds.max_end));
}

/** End just after word i, never reaching into the next word. */
export function endFromWord(words: Word[], i: number, bounds: Bounds): number {
  const w = words[i];
  let end = w.end + TAIL;
  if (i + 1 < words.length) end = Math.min(end, words[i + 1].start - GUARD);
  end = Math.max(end, w.end);
  return round2(clamp(end, bounds.min_start, bounds.max_end));
}

export function nudge(value: number, delta: number, lo: number, hi: number): number {
  return round2(clamp(value + delta, lo, hi));
}
