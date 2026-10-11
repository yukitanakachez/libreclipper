import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { onChanged } from "../changes";
import NewSheet from "./NewSheet";

vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { ...real.api, listCampaigns: vi.fn(), createJob: vi.fn(), chooseFile: vi.fn() } };
});

beforeEach(() => {
  vi.mocked(api.listCampaigns).mockResolvedValue([
    { slug: "pod", name: "Pod", valid: true, error: null },
    { slug: "old", name: null, valid: false, error: "min_len is required" }]);
});

afterEach(() => { window.location.hash = ""; });

describe("NewSheet", () => {
  it("starts a clip job from a YouTube link and opens it", async () => {
    vi.mocked(api.createJob).mockResolvedValue({ id: "vid9", existing: false });
    const onClose = vi.fn();
    render(<NewSheet onClose={onClose} />);
    await screen.findByRole("option", { name: "Pod" });
    await userEvent.type(screen.getByLabelText(/youtube link or file/i), "https://youtu.be/vid9");
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(api.createJob).toHaveBeenCalledWith("https://youtu.be/vid9", "pod");
    expect(window.location.hash).toBe("#/clips/vid9");
    expect(onClose).toHaveBeenCalled();
  });

  it("starts a clip job from a chosen file", async () => {
    vi.mocked(api.chooseFile).mockResolvedValue({ path: "/videos/episode.mp4" });
    vi.mocked(api.createJob).mockResolvedValue({ id: "episode", existing: false });
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("option", { name: "Pod" });
    await userEvent.click(screen.getByRole("button", { name: /choose file/i }));
    expect(await screen.findByDisplayValue("/videos/episode.mp4")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(api.createJob).toHaveBeenCalledWith("/videos/episode.mp4", "pod");
  });

  it("shows invalid campaigns as disabled with the reason", async () => {
    render(<NewSheet onClose={vi.fn()} />);
    expect(await screen.findByRole("option", { name: /old.*min_len/i })).toBeDisabled();
  });

  it("shows a clip job error inline, and stays open", async () => {
    vi.mocked(api.createJob).mockRejectedValue(new Error("That doesn't look like a YouTube link."));
    const onClose = vi.fn();
    render(<NewSheet onClose={onClose} />);
    await screen.findByRole("option", { name: "Pod" });
    await userEvent.type(screen.getByLabelText(/youtube link or file/i), "nope");
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(await screen.findByText(/doesn't look like a youtube link/i)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("");
  });

  it("has only the clip job form: no Clips/Stories switch", async () => {
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("dialog");
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByLabelText(/reddit link/i)).toBeNull();
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    render(<NewSheet onClose={onClose} />);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it('has a heading "New clip job"', async () => {
    render(<NewSheet onClose={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "New clip job" })).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "New clip job" })).toBeInTheDocument();
  });

  it("moves focus into the dialog on open and back to the opener button on Esc", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>+ New</button>
          {open && <NewSheet onClose={() => setOpen(false)} />}
        </>
      );
    }
    render(<Harness />);
    const button = screen.getByRole("button", { name: "+ New" });
    await userEvent.click(button);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    await userEvent.keyboard("{Escape}");
    expect(document.activeElement).toBe(button);
  });

  it("focuses the first form field on open", async () => {
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("dialog");
    expect(screen.getByLabelText(/youtube link or file/i)).toHaveFocus();
  });

  it("tells the list a new item exists", async () => {
    vi.mocked(api.createJob).mockResolvedValue({ id: "vid9", existing: false });
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("option", { name: "Pod" });
    await userEvent.type(screen.getByLabelText(/youtube link or file/i), "https://youtu.be/vid9");
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(heard).toHaveBeenCalled();
    stop();
  });
});
