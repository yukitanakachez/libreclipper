import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ShortcutList from "./ShortcutList";

const row = (list: HTMLElement, label: string) => within(list).getByText(label).closest("li")!;

describe("ShortcutList", () => {
  it("lists Open, Undo trim and closing a dialog with the others", () => {
    render(<ShortcutList />);
    const [main] = screen.getAllByRole("list");
    expect(row(main, "Open (Next up)")).toHaveTextContent("↵");
    expect(row(main, "Undo trim")).toHaveTextContent("⌘Z");
    expect(row(main, "Close a dialog")).toHaveTextContent("Esc");
  });

  it("names the board's and the workspace's keys: J/K between jobs or moments, ⌘↵ to render the clip", () => {
    render(<ShortcutList />);
    const [main] = screen.getAllByRole("list");
    expect(row(main, "Next / previous job or moment")).toHaveTextContent(/J.*K/);
    expect(row(main, "Render this clip")).toHaveTextContent("⌘↵");
    expect(row(main, "New")).toHaveTextContent("N");
    expect(within(main).queryByText(/approve & post|sidebar/i)).toBeNull();
  });

  it("no longer lists Preview, Approve, or the keys they had", () => {
    render(<ShortcutList />);
    const [main] = screen.getAllByRole("list");
    expect(within(main).queryByText(/preview|approve/i)).toBeNull();
    const chips = [...main.querySelectorAll(".kbd")].map((k) => k.textContent);
    expect(chips).toEqual(["J", "K", "↵", "⌘↵", "⌘Z", "N", "Esc", "?"]);
  });

  it("has a Transcript group for trimming by word", () => {
    render(<ShortcutList />);
    const transcript = screen.getByRole("list", { name: "Transcript" });
    expect(screen.getByRole("heading", { name: "Transcript" })).toBeInTheDocument();
    expect(row(transcript, "Start here")).toHaveTextContent(/Click.*↵/);
    expect(row(transcript, "End here")).toHaveTextContent(/⇧-click.*⇧↵/);
    expect(row(transcript, "Fix spelling")).toHaveTextContent(/Double-click.*F2/);
    expect(row(transcript, "Move between words")).toHaveTextContent(/←.*→/);
  });
});
