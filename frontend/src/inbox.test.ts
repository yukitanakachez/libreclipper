import { describe, expect, it } from "vitest";
import { buildNotifications } from "./inbox";
import { fromJob } from "./listItems";
import { job } from "./test-fixtures";

describe("buildNotifications", () => {
  it("is empty when nothing happened", () => {
    expect(buildNotifications([])).toEqual([]);
  });

  it("a job that is still working is not news", () => {
    expect(buildNotifications([fromJob(job({ state: "transcribing", busy: true })),
                               fromJob(job({ id: "vid2", state: "rendering", busy: true })),
                               fromJob(job({ id: "vid3", state: "queued" }))])).toEqual([]);
  });

  it("ready for review and rendered rows link to their job, once per job", () => {
    const notes = buildNotifications([
      fromJob(job({ id: "vid1", title: "Episode 1", state: "ready_for_review", updated_at: "2026-09-26T10:00:00Z" })),
      fromJob(job({ id: "vid2", title: "Episode 2", state: "done", clips: 3 })),
    ]);
    const byLead = Object.fromEntries(notes.map((n) => [n.lead, n]));
    expect(Object.keys(byLead).sort()).toEqual(["Ready for review:", "Rendered:"]);
    expect(byLead["Ready for review:"]).toMatchObject({ kind: "review", text: "Episode 1", sub: null,
                                                        href: "#/clips/vid1", key: "review:vid1" });
    expect(byLead["Rendered:"]).toMatchObject({ kind: "rendered", text: "Episode 2", sub: "3 clips",
                                                href: "#/clips/vid2", key: "rendered:vid2" });
  });

  it("every done job gets a Rendered note that counts its clips", () => {
    const notes = buildNotifications([fromJob(job({ id: "a", title: "A", state: "done", clips: 1 })),
                                      fromJob(job({ id: "b", title: "B", state: "done", clips: 4 }))]);
    expect(notes.map((n) => [n.key, n.kind, n.lead, n.text, n.sub])).toEqual([
      ["rendered:a", "rendered", "Rendered:", "A", "1 clip"],
      ["rendered:b", "rendered", "Rendered:", "B", "4 clips"],
    ]);
  });

  it("your own edits don't relight a review or rendered note: the key ignores updated_at", () => {
    const at = (t: string) => buildNotifications([
      fromJob(job({ id: "vid1", state: "ready_for_review", updated_at: t })),
      fromJob(job({ id: "vid2", state: "done", clips: 2, updated_at: t })),
    ]).map((n) => n.key);
    expect(at("2026-09-26T10:00:00Z")).toEqual(at("2026-09-26T11:30:00Z"));
  });

  it("a failed job names its step and explains the error in a plain sentence", () => {
    const notes = buildNotifications([
      fromJob(job({ id: "vid9", title: "Pod 9", state: "failed", failed_step: "pick", error: "boom\nstack" })),
      fromJob(job({ id: "vid8", title: "Pod 8", state: "failed", failed_step: "render",
                    error: "Could not resolve authentication method" })),
      fromJob(job({ id: "vid7", title: "Pod 7", state: "failed", failed_step: null, error: null })),
    ]);
    expect(notes.map((n) => [n.lead, n.text, n.sub, n.href])).toEqual([
      ["Picking failed:", "Pod 9", "boom", "#/clips/vid9"],
      ["Rendering failed:", "Pod 8", "Claude isn't signed in.", "#/clips/vid8"],
      ["Job failed:", "Pod 7", null, "#/clips/vid7"],
    ]);
  });

  it("a new failure of the same job is a new note: the key carries updated_at", () => {
    const failed = (t: string) => buildNotifications([
      fromJob(job({ id: "vid9", state: "failed", failed_step: "pick", updated_at: t }))])[0].key;
    expect(failed("2026-09-26T10:00:00Z")).toBe("failed:vid9:2026-09-26T10:00:00Z");
    expect(failed("2026-09-26T11:00:00Z")).not.toBe(failed("2026-09-26T10:00:00Z"));
  });

  it("puts failures first, then reviews, then renders", () => {
    const notes = buildNotifications([
      fromJob(job({ id: "a", state: "done", clips: 1 })),
      fromJob(job({ id: "b", state: "ready_for_review" })),
      fromJob(job({ id: "c", state: "failed", failed_step: "fetch" })),
    ]);
    expect(notes.map((n) => n.kind)).toEqual(["failed", "review", "rendered"]);
  });
});
