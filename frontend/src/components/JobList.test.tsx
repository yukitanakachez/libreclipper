import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { notifyChanged, onChanged } from "../changes";
import { job } from "../test-fixtures";
import { useJobList } from "../useJobList";
import JobList from "./JobList";

/** The board as App mounts it: fed by the one job-list poll. */
const Board = () => <JobList jobs={useJobList()} />;

vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { ...real.api, listJobs: vi.fn(), retry: vi.fn() } };
});

beforeEach(() => {
  vi.mocked(api.listJobs).mockResolvedValue([job({ id: "vid1", title: "Episode 1" }),
    job({ id: "vid2", title: "Episode 2", state: "failed", failed_step: "pick", error: "overloaded" })]);
});

afterEach(() => { window.location.hash = ""; });

const card = (name: RegExp) => screen.getByRole("link", { name });

describe("JobList", () => {
  it("J moves focus to the next card, K to the previous, without opening anything", async () => {
    render(<Board />);
    await screen.findByText("Needs you");
    await userEvent.keyboard("j");
    expect(card(/episode 1/i)).toHaveFocus();                 // nothing focused: J takes the first
    await userEvent.keyboard("j");
    expect(card(/episode 2/i)).toHaveFocus();
    await userEvent.keyboard("k");
    expect(card(/episode 1/i)).toHaveFocus();
    expect(window.location.hash).toBe("");
  });

  it("K does nothing at the first card, and J nothing at the last", async () => {
    render(<Board />);
    await screen.findByText("Needs you");
    await userEvent.keyboard("j");
    await userEvent.keyboard("k");
    expect(card(/episode 1/i)).toHaveFocus();
    await userEvent.keyboard("jjj");
    expect(card(/episode 2/i)).toHaveFocus();
  });

  it("with nothing focused, K takes the last card", async () => {
    render(<Board />);
    await screen.findByText("Needs you");
    await userEvent.keyboard("k");
    expect(card(/episode 2/i)).toHaveFocus();
  });

  it("J walks the cards in the order they are on screen: Needs you, Working, Finished", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      job({ id: "d", title: "Done one", state: "done", clips: 2 }),
      job({ id: "w", title: "Working one", state: "transcribing", busy: true }),
      job({ id: "n", title: "Needs one" })]);
    render(<Board />);
    await screen.findByText("Needs you");
    const seen: (string | null)[] = [];
    for (let i = 0; i < 3; i++) {
      await userEvent.keyboard("j");
      seen.push((document.activeElement as HTMLAnchorElement).getAttribute("href"));
    }
    expect(seen).toEqual(["#/clips/n", "#/clips/w", "#/clips/d"]);
  });

  it("↵ on the focused card opens it, as on any link", async () => {
    render(<Board />);
    await screen.findByText("Needs you");
    await userEvent.keyboard("jj");
    await userEvent.keyboard("{Enter}");
    expect(window.location.hash).toBe("#/clips/vid2");
  });

  it("J and K do nothing while the board is empty", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([]);
    render(<Board />);
    await waitFor(() => expect(document.querySelector(".skeleton")).toBeNull());
    await userEvent.keyboard("jk");
    expect(document.body).toHaveFocus();
  });

  it("a rendered job sits in Finished and says how many clips it made", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      job({ id: "vid1", title: "Episode 1", state: "done", clips: 3 }),
      job({ id: "vid2", title: "Episode 2", state: "done", clips: 1 })]);
    render(<Board />);
    const finished = (await screen.findByText("Finished")).closest("section")!;
    expect(finished).toHaveTextContent("Episode 1");
    expect(finished).toHaveTextContent("3 clips rendered · pod · 6 moments");
    expect(finished).toHaveTextContent("1 clip rendered · pod · 6 moments");
    expect(screen.queryByText("Needs you")).toBeNull();
    expect(screen.queryByText("Working")).toBeNull();
  });

  it("shows clip jobs in groups, with a count, linking to each", async () => {
    render(<Board />);
    expect(screen.getByRole("navigation", { name: "Clip jobs" })).toHaveClass("board");
    const needs = (await screen.findByText("Needs you")).closest("section")!;
    expect(needs.querySelector(".sec")).toHaveTextContent(/^Needs you2$/);
    expect(card(/episode 1/i)).toHaveAttribute("href", "#/clips/vid1");
    expect(card(/episode 1/i)).toHaveTextContent("Ready for review · pod · 6 moments");
    expect(card(/episode 2/i)).toHaveAttribute("href", "#/clips/vid2");
    expect(card(/episode 2/i).querySelector(".row-state")).toHaveClass("error");
  });

  it("retries a failed clip job with the clips API", async () => {
    vi.mocked(api.retry).mockResolvedValue({ queued: true });
    render(<Board />);
    expect(await screen.findByText("overloaded")).toBeInTheDocument();
    expect(screen.getByText("overloaded").closest(".problem")).toHaveAttribute("role", "status");
    await userEvent.click(screen.getByRole("button", { name: /retry from pick/i }));
    expect(api.retry).toHaveBeenCalledWith("vid2");
  });

  it("says why a retry was refused", async () => {
    vi.mocked(api.retry).mockRejectedValue(new ApiError(409, "Only failed jobs can be retried."));
    render(<Board />);
    await userEvent.click(await screen.findByRole("button", { name: /retry from pick/i }));
    expect(await screen.findByText("Only failed jobs can be retried.")).toBeInTheDocument();
  });

  it("a job that failed before any step retries from the start", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job({ state: "failed", failed_step: null, error: null })]);
    render(<Board />);
    expect(await screen.findByRole("button", { name: /retry from the start/i })).toBeInTheDocument();
    expect(document.querySelector(".problem")).toBeNull();
  });

  it("shows working jobs in Working with their step", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      job({ id: "vid1", title: "Episode 1", state: "transcribing", busy: true }),
      job({ id: "vid2", title: "Episode 2", state: "rendering", busy: true, progress: 0.4 })]);
    render(<Board />);
    const working = (await screen.findByText("Working")).closest("section")!;
    expect(card(/episode 1/i)).toHaveAttribute("href", "#/clips/vid1");
    expect(card(/episode 1/i)).toHaveTextContent(/Transcribing \d+:\d\d · pod · 6 moments/);
    expect(card(/episode 2/i)).toHaveTextContent("Rendering 40% · pod · 6 moments");
    expect(working.querySelectorAll(".progress")).toHaveLength(2);
    expect((card(/episode 2/i).querySelector(".progress > i") as HTMLElement).style.width).toBe("40%");
  });

  it("an empty board shows nothing of its own: Next up above it says how to start", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([]);
    render(<Board />);
    await waitFor(() => expect(document.querySelector(".skeleton")).toBeNull());
    expect(document.querySelector("section")).toBeNull();
    expect(screen.getByRole("navigation", { name: "Clip jobs" })).toBeEmptyDOMElement();
  });

  it("keeps the list when the server can't be reached", async () => {
    vi.mocked(api.listJobs).mockResolvedValueOnce([job({ id: "vid1", title: "Episode 1", state: "transcribing", busy: true })])
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<Board />);
    expect(await screen.findByText(/can't reach clipper/i, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("Episode 1")).toBeInTheDocument();
  });

  it("reloads when something changes elsewhere, even with nothing working", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job({ state: "done", clips: 1 })]);
    render(<Board />);
    await screen.findByText("Finished");
    vi.mocked(api.listJobs).mockResolvedValue([job({ state: "done", clips: 1 }),
      job({ id: "vid-new", title: "Brand new", state: "queued" })]);
    act(() => notifyChanged());
    expect(await screen.findByText("Brand new")).toBeInTheDocument();
  });

  it("tells everyone after a retry", async () => {
    vi.mocked(api.retry).mockResolvedValue({ queued: true });
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<Board />);
    await userEvent.click(await screen.findByRole("button", { name: /retry from pick/i }));
    expect(heard).toHaveBeenCalled();
    stop();
  });

  it("shows skeleton rows while loading", () => {
    vi.mocked(api.listJobs).mockReturnValue(new Promise(() => {}));
    render(<Board />);
    expect(document.querySelectorAll(".skeleton")).toHaveLength(3);
  });

  it("shows a first-load error instead of skeletons", async () => {
    vi.mocked(api.listJobs).mockRejectedValueOnce(new ApiError(500, "boom"));
    render(<Board />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(document.querySelectorAll(".skeleton")).toHaveLength(0);
  });

  it("leaves the indeterminate progress bar without an inline width, so the CSS animation shows it", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job({ state: "transcribing", busy: true })]);
    render(<Board />);
    await screen.findByText("Working");
    const bar = document.querySelector(".progress.indeterminate > i");
    expect(bar).not.toBeNull();
    expect(bar?.getAttribute("style")).toBeNull();
  });
});

describe("JobList avatars", () => {
  it("each row starts with its own orb, not a gradient square", async () => {
    render(<Board />);
    await screen.findByText("Episode 1");
    const rows = Array.from(document.querySelectorAll("a.row-item"));
    expect(rows.length).toBeGreaterThan(1);
    for (const r of rows) expect(r.querySelector(".orb")).not.toBeNull();
    expect(document.querySelector(".thumb, .g1, .g2, .g3, .g4")).toBeNull();
  });

  it("the failed row's Retry carries an icon", async () => {
    render(<Board />);
    const retry = await screen.findByRole("button", { name: /retry from pick/i });
    expect(retry.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
  });
});
