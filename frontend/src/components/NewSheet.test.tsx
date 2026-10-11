import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { onChanged } from "../changes";
import NewSheet from "./NewSheet";

vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { ...real.api, listCampaigns: vi.fn(), createJob: vi.fn(), chooseFile: vi.fn(),
                            uploadVideo: vi.fn() } };
});

beforeEach(() => {
  vi.mocked(api.listCampaigns).mockResolvedValue([
    { slug: "pod", name: "Pod", valid: true, error: null },
    { slug: "old", name: null, valid: false, error: "min_len is required" }]);
});

afterEach(() => { window.location.hash = ""; });

const zone = () => screen.getByRole("button", { name: /^video file/i });

/** Clicks the drop area and "chooses" this file in the computer's file chooser. */
async function chooseFile(path: string) {
  vi.mocked(api.chooseFile).mockResolvedValue({ path });
  await userEvent.click(zone());
  await screen.findByText(path.split("/").pop()!);
}

describe("NewSheet", () => {
  it("clicking the drop area opens the file chooser; the chosen video starts a job and opens it", async () => {
    vi.mocked(api.createJob).mockResolvedValue({ id: "vid9", existing: false });
    const onClose = vi.fn();
    render(<NewSheet onClose={onClose} />);
    await screen.findByRole("option", { name: "Pod" });
    expect(zone()).toHaveTextContent(/drop a video here/i);
    expect(screen.getByRole("button", { name: /^start$/i })).toBeDisabled();       // nothing chosen yet
    await chooseFile("/videos/vid9.mp4");
    expect(zone()).toHaveAccessibleName(/vid9\.mp4/);
    expect(api.uploadVideo).not.toHaveBeenCalled();                               // chosen in place: no copy
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(api.createJob).toHaveBeenCalledWith("/videos/vid9.mp4", "pod", "");
    expect(window.location.hash).toBe("#/clips/vid9");
    expect(onClose).toHaveBeenCalled();
  });

  it("the creator you type is sent with the job, to be credited on its clips", async () => {
    vi.mocked(api.createJob).mockClear();
    vi.mocked(api.createJob).mockResolvedValue({ id: "vid9", existing: false });
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("option", { name: "Pod" });
    await chooseFile("/videos/vid9.mp4");
    const creator = screen.getByRole("textbox", { name: /creator/i });
    expect(creator).toHaveAccessibleDescription(/credited on the clip/i);
    await userEvent.type(creator, " @JaneDoe ");
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(api.createJob).toHaveBeenCalledWith("/videos/vid9.mp4", "pod", "@JaneDoe");
  });

  it("a video dropped on the area is copied in, with progress, then starts a job", async () => {
    let finish!: (v: { path: string }) => void;
    vi.mocked(api.uploadVideo).mockImplementation((_file, onProgress) => {
      onProgress?.(0.42);
      return new Promise((resolve) => { finish = resolve; });
    });
    vi.mocked(api.createJob).mockResolvedValue({ id: "episode", existing: false });
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("option", { name: "Pod" });
    const file = new File(["x"], "Episode 12.mov", { type: "video/quicktime" });
    fireEvent.drop(zone(), { dataTransfer: { files: [file] } });
    expect(await screen.findByText(/copying episode 12\.mov… 42%/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^start$/i })).toBeDisabled();       // not while copying
    finish({ path: "/clipper/jobs/uploads/Episode 12.mov" });
    expect(await screen.findByText("Episode 12.mov")).toBeInTheDocument();
    expect(vi.mocked(api.uploadVideo).mock.calls[0][0]).toBe(file);
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(api.createJob).toHaveBeenCalledWith("/clipper/jobs/uploads/Episode 12.mov", "pod", "");
  });

  it("where the server can't open a file chooser, the browser's own is used instead", async () => {
    vi.mocked(api.chooseFile).mockRejectedValue(new ApiError(501, "Paste the video's file path instead."));
    const opened = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("option", { name: "Pod" });
    await userEvent.click(zone());
    expect(opened).toHaveBeenCalled();
    expect(screen.queryByText(/paste the video/i)).toBeNull();                    // not shown as an error
    opened.mockRestore();
  });

  it("a copy that fails says why, and the area is ready for another try", async () => {
    vi.mocked(api.uploadVideo).mockRejectedValue(new Error("That file is empty."));
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("option", { name: "Pod" });
    fireEvent.drop(zone(), { dataTransfer: { files: [new File([], "empty.mp4")] } });
    expect(await screen.findByText("That file is empty.")).toBeInTheDocument();
    expect(zone()).toHaveTextContent(/drop a video here/i);
    expect(zone()).toBeEnabled();
  });

  it("shows invalid campaigns as disabled with the reason", async () => {
    render(<NewSheet onClose={vi.fn()} />);
    expect(await screen.findByRole("option", { name: /old.*min_len/i })).toBeDisabled();
  });

  it("shows a clip job error inline, and stays open", async () => {
    vi.mocked(api.createJob).mockRejectedValue(new Error("No video file at /nope."));
    const onClose = vi.fn();
    render(<NewSheet onClose={onClose} />);
    await screen.findByRole("option", { name: "Pod" });
    await chooseFile("/nope.mp4");
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(await screen.findByText(/no video file at/i)).toBeInTheDocument();
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

  it("focuses the drop area on open", async () => {
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("dialog");
    expect(zone()).toHaveFocus();
  });

  it("tells the list a new item exists", async () => {
    vi.mocked(api.createJob).mockResolvedValue({ id: "vid9", existing: false });
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<NewSheet onClose={vi.fn()} />);
    await screen.findByRole("option", { name: "Pod" });
    await chooseFile("/videos/vid9.mp4");
    await userEvent.click(screen.getByRole("button", { name: /^start$/i }));
    expect(heard).toHaveBeenCalled();
    stop();
  });
});
