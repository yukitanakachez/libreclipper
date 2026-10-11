import { describe, expect, it } from "vitest";
import { fromJob, groupItems, itemStatus, oldestNeeds } from "./listItems";
import { job } from "./test-fixtures";

describe("list items", () => {
  it("groups by what needs you", () => {
    const items = [
      fromJob(job({ id: "a", state: "ready_for_review" })),
      fromJob(job({ id: "b", state: "failed", failed_step: "render", error: "x" })),
      fromJob(job({ id: "c", state: "transcribing" })),
      fromJob(job({ id: "d", state: "rendering" })),
      fromJob(job({ id: "e", state: "done" })),
    ];
    const g = groupItems(items);
    expect(g.needs.map((i) => i.id)).toEqual(["a", "b"]);
    expect(g.working.map((i) => i.id)).toEqual(["c", "d"]);
    expect(g.ready.map((i) => i.id)).toEqual(["e"]);
  });

  it("a done job is finished, not waiting on you, and says how many clips it rendered", () => {
    const items = [
      fromJob(job({ id: "a", state: "done", clips: 3 })),
      fromJob(job({ id: "b", state: "done", clips: 1 })),
      fromJob(job({ id: "c", state: "done", clips: 0 })),
    ];
    const g = groupItems(items);
    expect(g.needs).toEqual([]);
    expect(g.ready.map((i) => i.id)).toEqual(["a", "b", "c"]);
    expect(items.map(itemStatus)).toEqual(["3 clips rendered", "1 clip rendered", "Done"]);
    expect(itemStatus(fromJob(job({ state: "ready_for_review" })))).toBe("Ready for review");
    expect(itemStatus(fromJob(job({ state: "rendering", clips: 2 })))).toBe("Rendering");
  });

  it("a done job also says how many of its clips are posted", () => {
    const status = (clips: number, posted: number) => itemStatus(fromJob(job({ state: "done", clips, posted })));
    expect(status(3, 0)).toBe("3 clips rendered");
    expect(status(3, 1)).toBe("3 clips rendered · 1 posted");
    expect(status(3, 2)).toBe("3 clips rendered · 2 posted");
    expect(status(3, 3)).toBe("3 clips rendered · all posted");
    expect(status(1, 1)).toBe("1 clip rendered · all posted");
    expect(status(0, 0)).toBe("Done");
    expect(itemStatus(fromJob(job({ state: "ready_for_review", clips: 2, posted: 1 })))).toBe("Ready for review");
  });

  it("oldestNeeds picks the longest-waiting item that needs you, nulls last", () => {
    expect(oldestNeeds([])).toBeNull();
    const newer = fromJob(job({ id: "a", state: "ready_for_review", updated_at: "2026-09-25T10:00:00Z" }));
    const older = fromJob(job({ id: "b", state: "failed", updated_at: "2026-09-20T10:00:00Z" }));
    const noDate = fromJob(job({ id: "c", state: "failed", updated_at: null }));
    expect(oldestNeeds([newer, older, noDate])?.id).toBe("b");
    expect(oldestNeeds([noDate])?.id).toBe("c");
  });

  it("titles fall back sensibly", () => {
    expect(fromJob(job({ title: null, source: "/x/ep.mp4" })).title).toBe("/x/ep.mp4");
    expect(fromJob(job({ id: "vid7", title: null, source: null })).title).toBe("vid7");
    expect(fromJob(job()).subtitle).toBe("pod · 6 moments");
    expect(fromJob(job({ campaign: null, candidates: 2 })).subtitle).toBe("— · 2 moments");
  });

  it("carries the moment, clip and posted counts", () => {
    expect(fromJob(job({ candidates: 6, clips: 2, posted: 1 }))).toMatchObject({ candidates: 6, clips: 2, posted: 1 });
  });
});
