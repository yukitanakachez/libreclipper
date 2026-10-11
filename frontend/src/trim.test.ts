import { describe, expect, it } from "vitest";
import { endFromWord, nudge, startFromWord } from "./trim";

const words = [
  { i: 0, text: "a", start: 1.0, end: 1.4 },
  { i: 1, text: "b", start: 1.42, end: 1.8 },
  { i: 2, text: "c.", start: 3.0, end: 3.4 },
];
const bounds = { min_start: 0.5, max_end: 3.5 };

describe("trim", () => {
  it("starts a little before the clicked word", () => {
    expect(startFromWord(words, 2, bounds)).toBeCloseTo(2.9);
  });
  it("never reaches back into the previous word", () => {
    expect(startFromWord(words, 1, bounds)).toBeCloseTo(1.42);   // prev ends 1.4; guard pushes past start → clamp to word start
  });
  it("ends a little after the clicked word, clear of the next", () => {
    expect(endFromWord(words, 1, bounds)).toBeCloseTo(2.1);
    expect(endFromWord(words, 0, bounds)).toBeCloseTo(1.4);      // next word starts at 1.42
  });
  it("stays inside the analyzed range", () => {
    expect(endFromWord(words, 2, bounds)).toBe(3.5);
    expect(startFromWord([{ i: 0, text: "x", start: 0.55, end: 0.9 }], 0, bounds)).toBe(0.5);
  });
  it("nudges within bounds", () => {
    expect(nudge(1.0, -0.5, 0.8, 5)).toBe(0.8);
    expect(nudge(1.0, 0.5, 0, 5)).toBe(1.5);
  });
});
