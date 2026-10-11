import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import useShortcuts from "./useShortcuts";

function Harness({ map, enabled }: { map: Record<string, () => void>; enabled?: boolean }) {
  useShortcuts(map, enabled);
  return (
    <div>
      <textarea aria-label="Notes" />
      <input aria-label="Title" />
      <button>Just a button</button>
    </div>
  );
}

afterEach(() => {
  document.querySelectorAll("dialog").forEach((d) => d.remove());
});

describe("useShortcuts", () => {
  it("shortcuts fire on the page", async () => {
    const j = vi.fn();
    render(<Harness map={{ j }} />);
    await userEvent.keyboard("j");
    expect(j).toHaveBeenCalledTimes(1);
  });

  it("typing in a textarea or input never triggers them", async () => {
    const spies = { j: vi.fn(), k: vi.fn(), n: vi.fn() };
    render(<Harness map={spies} />);
    await userEvent.type(screen.getByLabelText("Notes"), "jkn");
    expect(spies.j).not.toHaveBeenCalled();
    expect(spies.k).not.toHaveBeenCalled();
    expect(spies.n).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Title"), "jkn");
    expect(spies.j).not.toHaveBeenCalled();
  });

  it("nothing fires while a dialog is open", async () => {
    const j = vi.fn();
    render(<Harness map={{ j }} />);
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    document.body.appendChild(dialog);
    await userEvent.keyboard("j");
    expect(j).not.toHaveBeenCalled();
    dialog.remove();
    await userEvent.keyboard("j");
    expect(j).toHaveBeenCalledTimes(1);
  });

  it("mod+z fires with ⌘Z only, and not while typing", () => {
    const undo = vi.fn();
    render(<><Harness map={{ "mod+z": undo }} /><input aria-label="field" /></>);
    fireEvent.keyDown(document, { key: "z" });
    fireEvent.keyDown(document, { key: "z", metaKey: true, shiftKey: true });
    expect(undo).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "z", metaKey: true });
    expect(undo).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByRole("textbox", { name: "field" }), { key: "z", metaKey: true });
    expect(undo).toHaveBeenCalledTimes(1);
  });

  it("mod+enter needs the modifier", async () => {
    const post = vi.fn();
    render(<Harness map={{ "mod+enter": post }} />);
    fireEvent.keyDown(document, { key: "Enter" });
    expect(post).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "Enter", metaKey: true });
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("? fires even with shift held, since that's how it's typed", () => {
    const help = vi.fn();
    render(<Harness map={{ "?": help }} />);
    fireEvent.keyDown(document, { key: "?", shiftKey: true });
    expect(help).toHaveBeenCalledTimes(1);
  });

  it("ignores a plain-key shortcut when another modifier is held", () => {
    const j = vi.fn();
    render(<Harness map={{ j }} />);
    fireEvent.keyDown(document, { key: "j", ctrlKey: true });
    fireEvent.keyDown(document, { key: "j", metaKey: true });
    fireEvent.keyDown(document, { key: "j", altKey: true });
    fireEvent.keyDown(document, { key: "j", shiftKey: true });
    expect(j).not.toHaveBeenCalled();
  });

  it("mod+z accepts ctrlKey off Mac", () => {
    const undo = vi.fn();
    render(<Harness map={{ "mod+z": undo }} />);
    fireEvent.keyDown(document, { key: "z", ctrlKey: true });
    expect(undo).toHaveBeenCalledTimes(1);
  });

  it("P, A, E and ⌘\\ are no longer shortcuts, even when something maps them", () => {
    const spies = { p: vi.fn(), a: vi.fn(), e: vi.fn(), "mod+e": vi.fn(), "mod+\\": vi.fn() };
    render(<Harness map={spies} />);
    for (const key of ["p", "a", "e"]) fireEvent.keyDown(document, { key });
    fireEvent.keyDown(document, { key: "e", metaKey: true });
    fireEvent.keyDown(document, { key: "\\", metaKey: true });
    fireEvent.keyDown(document, { key: "\\", ctrlKey: true });
    for (const spy of Object.values(spies)) expect(spy).not.toHaveBeenCalled();
  });

  it("N is a plain key: no modifiers, not in a field, not with a dialog open", async () => {
    const n = vi.fn();
    render(<Harness map={{ n }} />);
    fireEvent.keyDown(document, { key: "n", metaKey: true });
    fireEvent.keyDown(document, { key: "n", ctrlKey: true });
    expect(n).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Title"), "n");
    expect(n).not.toHaveBeenCalled();
    await userEvent.click(document.body);
    await userEvent.keyboard("n");
    expect(n).toHaveBeenCalledTimes(1);
  });

  it("plain Enter fires 'enter', and ⌘Enter still fires 'mod+enter' only", () => {
    const enter = vi.fn();
    const post = vi.fn();
    render(<Harness map={{ enter, "mod+enter": post }} />);
    fireEvent.keyDown(document, { key: "Enter" });
    expect(enter).toHaveBeenCalledTimes(1);
    expect(post).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "Enter", metaKey: true });
    expect(post).toHaveBeenCalledTimes(1);
    expect(enter).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Enter", shiftKey: true });
    expect(enter).toHaveBeenCalledTimes(1);
  });

  it("Enter on a focused button or in a field is left alone", async () => {
    const enter = vi.fn();
    render(<Harness map={{ enter }} />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Just a button" }), { key: "Enter" });
    await userEvent.type(screen.getByLabelText("Title"), "{Enter}");
    expect(enter).not.toHaveBeenCalled();
  });

  it("enabled=false suppresses every shortcut", async () => {
    const j = vi.fn();
    render(<Harness map={{ j }} enabled={false} />);
    await userEvent.keyboard("j");
    expect(j).not.toHaveBeenCalled();
  });

  it("an unmapped key is a no-op, not an error", async () => {
    render(<Harness map={{ j: vi.fn() }} />);
    await userEvent.keyboard("z");
  });
});
