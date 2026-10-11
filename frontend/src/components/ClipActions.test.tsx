import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { onChanged } from "../changes";
import { clip } from "../test-fixtures";
import ClipActions from "./ClipActions";

vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { setPosted: vi.fn(), reveal: vi.fn() } };
});

const POSTED = "2026-09-25T10:00:00Z";
const clipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

afterEach(() => {
  if (clipboard) Object.defineProperty(navigator, "clipboard", clipboard);
  else delete (navigator as { clipboard?: unknown }).clipboard;
});

describe("ClipActions", () => {
  it("offers Mark posted, Copy caption and Show in Finder", () => {
    render(<ClipActions jobId="vid1" clip={clip()} />);
    expect(screen.getAllByRole("button").map((b) => b.textContent))
      .toEqual(["Mark posted", "Copy caption", "Show in Finder"]);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("Mark posted marks the clip posted and tells everyone", async () => {
    vi.mocked(api.setPosted).mockResolvedValue(clip({ posted_at: POSTED }));
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<ClipActions jobId="vid1" clip={clip()} />);
    const toggle = screen.getByRole("button", { name: "Mark posted" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(toggle).not.toHaveClass("on");
    expect(toggle).toHaveAttribute("title", "Mark this clip as posted");
    await userEvent.click(toggle);
    expect(api.setPosted).toHaveBeenCalledWith("vid1", "01-one.mp4", true);
    await waitFor(() => expect(heard).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("status")).toBeNull();                     // the reloaded clip is the feedback
    stop();
  });

  it("a posted clip reads Posted, pressed; pressing it takes that back", async () => {
    vi.mocked(api.setPosted).mockResolvedValue(clip());
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<ClipActions jobId="vid 2" clip={clip({ file: "02 two.mp4", posted_at: POSTED })} />);
    const toggle = screen.getByRole("button", { name: "Posted" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(toggle).toHaveClass("on");
    expect(toggle).toHaveAttribute("title", "Posted: press to mark it not posted");
    expect(screen.queryByRole("button", { name: "Mark posted" })).toBeNull();
    await userEvent.click(toggle);
    expect(api.setPosted).toHaveBeenCalledWith("vid 2", "02 two.mp4", false);
    await waitFor(() => expect(heard).toHaveBeenCalledTimes(1));
    stop();
  });

  it("follows the clip it is given: Posted once the reload says so", () => {
    const { rerender } = render(<ClipActions jobId="vid1" clip={clip()} />);
    rerender(<ClipActions jobId="vid1" clip={clip({ posted_at: POSTED })} />);
    expect(screen.getByRole("button", { name: "Posted" })).toHaveAttribute("aria-pressed", "true");
  });

  it("says why the clip couldn't be marked, tells no one, and clears the note on the next try", async () => {
    vi.mocked(api.setPosted).mockRejectedValueOnce(new ApiError(404, "No clip called '01-one.mp4'."))
      .mockResolvedValueOnce(clip({ posted_at: POSTED }));
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<ClipActions jobId="vid1" clip={clip()} />);
    await userEvent.click(screen.getByRole("button", { name: "Mark posted" }));
    const note = await screen.findByRole("status");
    expect(note).toHaveTextContent("No clip called '01-one.mp4'.");
    expect(note).toHaveClass("error");
    expect(heard).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Mark posted" })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: "Mark posted" }));
    await waitFor(() => expect(heard).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("status")).toBeNull();
    stop();
  });

  it("Copy caption copies the clip's caption and says so", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
    render(<ClipActions jobId="vid1" clip={clip({ caption: "Line one\n\n#pod #clips" })} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy caption" }));
    expect(writeText).toHaveBeenCalledWith("Line one\n\n#pod #clips");
    const note = await screen.findByRole("status");
    expect(note).toHaveTextContent("Copied caption + hashtags");
    expect(note).toHaveClass("muted");
    expect(api.setPosted).not.toHaveBeenCalled();
  });

  it("says where the text is when it can't be copied", async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error("denied")));
    render(<ClipActions jobId="vid1" clip={clip()} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy caption" }));
    const note = await screen.findByRole("status");
    expect(note).toHaveTextContent("Couldn't copy: the text is in the .txt file next to the video.");
    expect(note).toHaveClass("error");
  });

  it("Show in Finder reveals the clip's file, and says why when it can't", async () => {
    vi.mocked(api.reveal).mockResolvedValueOnce({ revealed: true })
      .mockRejectedValueOnce(new ApiError(404, "That file is gone."));
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<ClipActions jobId="vid1" clip={clip()} />);
    const button = screen.getByRole("button", { name: "Show in Finder" });
    await userEvent.click(button);
    expect(api.reveal).toHaveBeenCalledWith("vid1", "01-one.mp4");
    expect(screen.queryByRole("status")).toBeNull();
    await userEvent.click(button);
    expect(await screen.findByRole("status")).toHaveTextContent("That file is gone.");
    expect(screen.getByRole("status")).toHaveClass("error");
    expect(heard).not.toHaveBeenCalled();                                 // nothing changed
    stop();
  });
});
