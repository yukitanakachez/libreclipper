import { describe, expect, it } from "vitest";
import { elapsed, formatSeconds, stateLabel } from "./labels";

describe("labels", () => {
  it("names a clip job's states in plain words, and passes unknown ones through", () => {
    expect(stateLabel("fetching")).toBe("Downloading");
    expect(stateLabel("picking")).toBe("Picking moments");
    expect(stateLabel("ready_for_review")).toBe("Ready for review");
    expect(stateLabel("voicing")).toBe("voicing");                      // a story state: gone
  });

  it("formats elapsed time since a step started", () => {
    const start = "2026-09-24T10:00:00Z";
    expect(elapsed(start, Date.parse("2026-09-24T10:01:05Z"))).toBe("1:05");
    expect(elapsed(start, Date.parse("2026-09-24T09:59:00Z"))).toBe("0:00");  // clock skew
  });
  it("formats clip times", () => {
    expect(formatSeconds(75.25)).toBe("1:15.3");
  });
});
