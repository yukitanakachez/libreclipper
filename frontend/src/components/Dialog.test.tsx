import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Dialog from "./Dialog";

function Harness({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      {open && (
        <Dialog title="A dialog" onClose={() => { setOpen(false); onClose(); }}>
          <button>Inside</button>
        </Dialog>
      )}
    </>
  );
}

describe("Dialog", () => {
  it("shows a visible heading with the title", async () => {
    render(<Dialog title="A dialog" onClose={vi.fn()}><button>Inside</button></Dialog>);
    expect(await screen.findByRole("heading", { name: "A dialog" })).toBeInTheDocument();
  });

  it("moves focus inside on open and back to the opener on close", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole("button", { name: "Open" });
    await userEvent.click(opener);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
    expect(document.activeElement).toBe(opener);
  });

  it("closes when the click target is the dialog itself, not its content", async () => {
    const onClose = vi.fn();
    render(<Dialog title="A dialog" onClose={onClose}><button>Inside</button></Dialog>);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Inside" }));
    expect(onClose).not.toHaveBeenCalled();
    await userEvent.click(dialog);
    expect(onClose).toHaveBeenCalled();
  });

  it("does not close on a click in the content wrapper's own padding/gap, only on the dialog element itself", async () => {
    const onClose = vi.fn();
    render(<Dialog title="A dialog" onClose={onClose}><button>Inside</button></Dialog>);
    const dialog = await screen.findByRole("dialog");
    const body = dialog.querySelector(".dialog-body");
    expect(body).not.toBeNull();
    await userEvent.click(body as HTMLElement);
    expect(onClose).not.toHaveBeenCalled();
    await userEvent.click(dialog);
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose exactly once when a cancel event and an Escape keydown both fire for the same close", async () => {
    const onClose = vi.fn();
    render(<Dialog title="A dialog" onClose={onClose}><button>Inside</button></Dialog>);
    const dialog = await screen.findByRole("dialog");
    dialog.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    dialog.dispatchEvent(new Event("cancel", { cancelable: true }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
