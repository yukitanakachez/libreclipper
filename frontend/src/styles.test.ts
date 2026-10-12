/// <reference types="node" />
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Read as text from disk (tests run from frontend/): importing it would hand back processed CSS.
const css = readFileSync("src/styles.css", "utf8");

/** Every rule's selector list, with comments removed (a comment may sit inside a list). */
function selectorLists(source: string): string[] {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").split("}").map((rule) => rule.split("{")[0].trim()).filter(Boolean);
}

describe("styles.css", () => {
  it("the skip link's rule belongs to the skip link alone", () => {
    // The page areas' ":focus { outline: none }" once lost its body, so its selectors ran on
    // into the skip link's rule: clicking empty space focused the workspace, which then took
    // the skip link's absolute position and shrank into a small card in the corner.
    const withSkipLink = selectorLists(css).filter((list) => /\.skip-link(?![\w-])/.test(list));
    expect(withSkipLink.length).toBeGreaterThan(0);
    for (const list of withSkipLink) {
      expect(list.split(",").map((s) => s.trim()).every((s) => s.startsWith(".skip-link"))).toBe(true);
    }
  });

  it("no rule is left without a body", () => {
    // "a, b," straight before another rule is the same accident in general.
    expect(selectorLists(css).filter((list) => /,\s*$/.test(list))).toEqual([]);
  });
});
