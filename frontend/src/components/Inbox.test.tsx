import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Notification } from "../inbox";
import Inbox from "./Inbox";

const note = (key: string, lead: string, text = "", over: Partial<Notification> = {}): Notification =>
  ({ key, kind: "review", lead, text, sub: null, href: "#/clips/vid1", ...over });

const NOTES = [
  note("failed:vid3:t", "Rendering failed:", "Ring", { kind: "failed", sub: "ffmpeg said no", href: "#/clips/vid3" }),
  note("review:vid1", "Ready for review:", "Episode 1"),
  note("rendered:vid2", "Rendered:", "Host family", { kind: "rendered", sub: "3 clips", href: "#/clips/vid2" }),
];

beforeEach(() => { localStorage.clear(); window.location.hash = ""; });
afterEach(() => { vi.restoreAllMocks(); });

const bell = () => screen.getByRole("button", { name: /^inbox/i });

describe("Inbox", () => {
  it("the bell says how many are unread and carries the dot", () => {
    render(<Inbox notes={NOTES} />);
    expect(bell()).toHaveAccessibleName("Inbox, 3 unread");
    expect(bell()).toHaveAttribute("aria-expanded", "false");
    expect(bell().querySelector(".pip")).not.toBeNull();
  });

  it("opens under the bell, moves focus in, and lists the notes", async () => {
    render(<Inbox notes={NOTES} />);
    await userEvent.click(bell());
    expect(bell()).toHaveAttribute("aria-expanded", "true");
    const pop = screen.getByRole("dialog", { name: "Inbox" });
    expect(pop).not.toHaveAttribute("aria-modal", "true");
    expect(pop.contains(document.activeElement)).toBe(true);
    expect(within(pop).getByRole("link", { name: /rendering failed: ring ffmpeg said no/i }))
      .toHaveAttribute("href", "#/clips/vid3");
    expect(within(pop).getByRole("link", { name: /ready for review: episode 1/i })).toHaveAttribute("href", "#/clips/vid1");
    expect(within(pop).getByRole("link", { name: /rendered: host family 3 clips/i })).toHaveAttribute("href", "#/clips/vid2");
    for (const link of within(pop).getAllByRole("link")) {          // each kind has its icon
      expect(link.querySelector('.note-ic svg')).not.toBeNull();
    }
  });

  it("opening a note marks it read, and that survives a reload", async () => {
    const { unmount } = render(<Inbox notes={NOTES} />);
    await userEvent.click(bell());
    await userEvent.click(screen.getByRole("link", { name: /rendered: host family/i }));
    expect(window.location.hash).toBe("#/clips/vid2");
    expect(bell()).toHaveAccessibleName("Inbox, 2 unread");
    expect(JSON.parse(localStorage.getItem("clipper.inbox.read")!)).toEqual(["rendered:vid2"]);
    unmount();
    render(<Inbox notes={NOTES} />);
    expect(bell()).toHaveAccessibleName("Inbox, 2 unread");
  });

  it("Mark all read clears the count and the dot", async () => {
    render(<Inbox notes={NOTES} />);
    await userEvent.click(bell());
    await userEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(bell()).toHaveAccessibleName("Inbox");
    expect(bell().querySelector(".pip")).toBeNull();
    expect(JSON.parse(localStorage.getItem("clipper.inbox.read")!).sort())
      .toEqual(NOTES.map((n) => n.key).sort());
  });

  it("bad or throwing storage counts everything unread, and clicking still works", async () => {
    localStorage.setItem("clipper.inbox.read", "{not json");
    const first = render(<Inbox notes={NOTES} />);
    expect(bell()).toHaveAccessibleName("Inbox, 3 unread");
    first.unmount();

    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<Inbox notes={NOTES} />);
    expect(bell()).toHaveAccessibleName("Inbox, 3 unread");
    await userEvent.click(bell());
    await userEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(bell()).toHaveAccessibleName("Inbox");
  });

  it("Esc closes it and gives focus back to the bell", async () => {
    render(<Inbox notes={NOTES} />);
    await userEvent.click(bell());
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Inbox" })).toBeNull();
    expect(bell()).toHaveFocus();
    expect(bell()).toHaveAttribute("aria-expanded", "false");
  });

  it("a click outside closes it", async () => {
    render(<><Inbox notes={NOTES} /><p>elsewhere</p></>);
    await userEvent.click(bell());
    act(() => { fireEvent.pointerDown(screen.getByText("elsewhere")); });
    expect(screen.queryByRole("dialog", { name: "Inbox" })).toBeNull();
  });

  it("says Nothing new when there is nothing", async () => {
    render(<Inbox notes={[]} />);
    expect(bell()).toHaveAccessibleName("Inbox");
    await userEvent.click(bell());
    expect(screen.getByText("Nothing new")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark all read" })).toBeNull();
  });
});

describe("Inbox read state across a new failure", () => {
  it("a second failure of the same job is unread even after reading the first", async () => {
    const fail = (at: string) => note(`failed:vid3:${at}`, "Rendering failed:", "Host family",
      { kind: "failed", href: "#/clips/vid3" });
    const { rerender } = render(<Inbox notes={[fail("10:00")]} />);
    await userEvent.click(bell());
    await userEvent.click(screen.getByRole("link", { name: /rendering failed/i }));
    expect(bell()).toHaveAccessibleName("Inbox");
    rerender(<Inbox notes={[fail("11:00")]} />);
    expect(bell()).toHaveAccessibleName("Inbox, 1 unread");
  });
});
