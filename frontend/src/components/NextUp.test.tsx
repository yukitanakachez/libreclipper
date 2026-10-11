import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fromJob, type ListItem } from "../listItems";
import { job } from "../test-fixtures";
import NextUp from "./NextUp";

const jobs = (over: { items?: ListItem[]; loaded?: boolean } = {}) => ({ items: [], loaded: true, ...over });

afterEach(() => { window.location.hash = ""; });

describe("NextUp", () => {
  it("names the oldest item that needs you and opens it", async () => {
    const older = fromJob(job({ id: "a", title: "Older job", state: "ready_for_review",
      updated_at: "2026-09-20T10:00:00Z" }));
    const newer = fromJob(job({ id: "b", title: "Newer job", state: "failed",
      updated_at: "2026-09-24T10:00:00Z" }));
    render(<NextUp jobs={jobs({ items: [newer, older] })} onNew={vi.fn()} />);
    expect(await screen.findByText("Older job")).toBeInTheDocument();
    expect(screen.queryByText("Newer job")).toBeNull();
    expect(screen.getByText("2 jobs need you.")).toBeInTheDocument();
    expect(screen.getByText("Ready for review · pod · 6 moments")).toBeInTheDocument();
    const open = screen.getByRole("link", { name: /open/i });
    expect(open).toHaveAttribute("href", "#/clips/a");
    expect(screen.queryByRole("button", { name: /new clip job/i })).toBeNull();
  });

  it("says 1 job needs you for one", () => {
    render(<NextUp jobs={jobs({ items: [fromJob(job())] })} onNew={vi.fn()} />);
    expect(screen.getByText("1 job needs you.")).toBeInTheDocument();
  });

  it("Enter opens the item it names, same as Open ↵", async () => {
    window.location.hash = "#/";
    const older = fromJob(job({ id: "a", title: "Older job", state: "ready_for_review",
      updated_at: "2026-09-20T10:00:00Z" }));
    render(<NextUp jobs={jobs({ items: [older] })} onNew={vi.fn()} />);
    await screen.findByText("Older job");
    await userEvent.keyboard("{Enter}");
    expect(window.location.hash).toBe("#/clips/a");
  });

  it("Enter does nothing when all caught up", async () => {
    window.location.hash = "#/";
    render(<NextUp jobs={jobs({ items: [fromJob(job({ id: "vid1", state: "done" }))] })}
                   onNew={vi.fn()} />);
    await screen.findByText(/all caught up/i);
    await userEvent.keyboard("{Enter}");
    expect(window.location.hash).toBe("#/");
  });

  it("Moments to review counts the moments across the clip jobs that need you", async () => {
    const clips = [
      fromJob(job({ id: "a", state: "ready_for_review", candidates: 6 })),
      fromJob(job({ id: "b", state: "ready_for_review", candidates: 4, updated_at: "2026-09-25T10:00:00Z" })),
      fromJob(job({ id: "c", state: "done", candidates: 9 })),
      fromJob(job({ id: "d", state: "failed", candidates: 5 })),
    ];
    render(<NextUp jobs={jobs({ items: clips })} onNew={vi.fn()} />);
    const tile = (await screen.findByText("Moments to review")).closest(".tile")!;
    expect(tile).toHaveTextContent("Moments to review10");
  });

  it("Rendered, not posted counts every job's clips that aren't posted yet, and leads to the Rendered page", async () => {
    const clips = [
      fromJob(job({ id: "a", state: "ready_for_review", clips: 1 })),
      fromJob(job({ id: "b", state: "done", clips: 3, posted: 1 })),
      fromJob(job({ id: "c", state: "done", clips: 2, posted: 2 })),
    ];
    render(<NextUp jobs={jobs({ items: clips })} onNew={vi.fn()} />);
    const tile = screen.getByRole("link", { name: /rendered, not posted/i });
    expect(tile).toHaveClass("tile");
    expect(tile).toHaveTextContent("Rendered, not posted3");
    expect(tile).toHaveAttribute("href", "#/rendered");
    expect(document.querySelectorAll(".tile")).toHaveLength(3);
    expect(screen.queryByText(/clips rendered|waiting to post/i)).toBeNull();
  });

  it("a rendered clip job doesn't need you: with only those, all caught up", async () => {
    const clips = [fromJob(job({ id: "vid1", title: "Rendered ep", state: "done", clips: 2 })),
                   fromJob(job({ id: "vid2", state: "transcribing", busy: true }))];
    render(<NextUp jobs={jobs({ items: clips })} onNew={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "All caught up" })).toBeInTheDocument();
    expect(screen.queryByText("Rendered ep")).toBeNull();
    expect(screen.queryByText(/needs? you/)).toBeNull();
    expect(screen.queryByText(/turn a video into clips/i)).toBeNull();
  });

  it("all caught up offers New clip job", async () => {
    const onNew = vi.fn();
    render(<NextUp jobs={jobs({
      items: [fromJob(job({ id: "vid1", state: "done" }))],
    })} onNew={onNew} />);
    expect(await screen.findByText(/all caught up/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New clip job" }));
    expect(onNew).toHaveBeenCalled();
  });

  it("with no jobs at all, a heading and New clip job, nothing more", async () => {
    const onNew = vi.fn();
    render(<NextUp jobs={jobs()} onNew={onNew} />);
    expect(screen.getByRole("heading", { name: "Turn a video into clips" })).toBeInTheDocument();
    expect(document.querySelector(".next-up p")).toBeNull();
    expect(screen.queryByText(/approve|preview/i)).toBeNull();
    expect(screen.queryByText(/all caught up/i)).toBeNull();
    const button = screen.getByRole("button", { name: "New clip job" });
    expect(button).toHaveClass("primary");
    await userEvent.click(button);
    expect(onNew).toHaveBeenCalled();
  });

  it("the Working tile shows the count and the first working item's state, lower-cased", async () => {
    const needs = fromJob(job({ id: "a", title: "Needs", state: "failed", updated_at: "2026-09-20T10:00:00Z" }));
    const working = fromJob(job({ id: "b", title: "Working one", state: "picking" }));
    const second = fromJob(job({ id: "c", title: "Working two", state: "rendering" }));
    render(<NextUp jobs={jobs({ items: [needs, working, second] })} onNew={vi.fn()} />);
    expect(await screen.findByText("2 · picking moments")).toBeInTheDocument();
  });

  it("the Working tile says Nothing when nothing is working", async () => {
    const needs = fromJob(job({ id: "a", title: "Needs", state: "failed", updated_at: "2026-09-20T10:00:00Z" }));
    render(<NextUp jobs={jobs({ items: [needs] })} onNew={vi.fn()} />);
    expect(await screen.findByText("Nothing")).toBeInTheDocument();
  });

  it("shows skeletons, not All caught up, while the first load is still pending", async () => {
    window.location.hash = "#/";
    render(<NextUp jobs={jobs({ loaded: false })} onNew={vi.fn()} />);
    expect(screen.queryByText(/all caught up|turn a video into clips/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /new/i })).toBeNull();
    expect(document.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
    await userEvent.keyboard("{Enter}");
    expect(window.location.hash).toBe("#/");
  });
});

describe("NextUp avatar", () => {
  it("the Next up card shows a 44 px orb for the item", async () => {
    const older = fromJob(job({ id: "a", title: "Older job", state: "ready_for_review",
      updated_at: "2026-09-20T10:00:00Z" }));
    render(<NextUp jobs={jobs({ items: [older] })} onNew={vi.fn()} />);
    await screen.findByText("Older job");
    const orb = document.querySelector(".next-card .orb") as HTMLElement;
    expect(orb).not.toBeNull();
    expect(orb.style.width).toBe("44px");
    expect(document.querySelector(".thumb, .g1, .g2, .g3, .g4")).toBeNull();
  });
});
