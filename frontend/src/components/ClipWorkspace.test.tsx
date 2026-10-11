import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { cand, clip, detail } from "../test-fixtures";
import { notifyChanged, onChanged } from "../changes";
import type { CandidateView, Clip } from "../types";
import ClipWorkspace from "./ClipWorkspace";

vi.mock("../announce");
vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { getJob: vi.fn(), patchCandidate: vi.fn(), saveWordFixes: vi.fn(), render: vi.fn(),
    repick: vi.fn(), retry: vi.fn(), setPosted: vi.fn(), reveal: vi.fn() } };
});

beforeEach(() => {
  vi.mocked(api.getJob).mockResolvedValue(detail());
});

const moments = () => within(screen.getByRole("navigation", { name: /moments/i }));
/** The selected moment's Render button ("Render again" once it has a clip). */
const renderButton = () => screen.findByRole("button", { name: /^render( again)?$/i });
const pickAgain = () => screen.findByRole("button", { name: "Pick again…" });
/** A job whose first moment (of two) is as given; `clips` are the job's rendered clips. */
const withOne = (over: Partial<CandidateView>, clips: Clip[] = []) =>
  detail({ candidates: [cand(over), cand({ n: 2, start: 15, end: 19.9, headline: "Two", score: 8 })], clips });
/** Moment 1 has a rendered clip. */
const rendered = (over: Partial<Clip> = {}) => withOne({ clip: "01-one.mp4" }, [clip(over)]);
const sourceVideo = () => document.querySelector(".device-screen video.source") as HTMLVideoElement | null;
const renderedVideo = () => document.querySelector(".device-screen video.rendered") as HTMLVideoElement | null;
/** The phone's Source · Rendered toggles. */
const phoneView = (name: "Source" | "Rendered") =>
  within(screen.getByRole("group", { name: /show in the phone/i }))
    .getByRole("button", { name: `Show ${name.toLowerCase()} in the phone` });
/** The server has news: the workspace reloads the job. */
const serverNow = (job: ReturnType<typeof detail>) => {
  vi.mocked(api.getJob).mockResolvedValue(job);
  act(() => notifyChanged());
};

describe("ClipWorkspace", () => {
  it("lists the moments with length, score and a way back to all clip jobs", async () => {
    render(<ClipWorkspace jobId="vid1" />);
    const one = await moments().findByRole("button", { name: /One/ });
    expect(one).toHaveTextContent("4.5 s");
    expect(within(one).getByText("9")).toHaveClass("score");
    expect(moments().getByRole("link", { name: /all clip jobs/i })).toHaveAttribute("href", "#/");
    expect(moments().getByText(/2 moments/)).toBeInTheDocument();
  });

  it("moment list shows Rendered for a moment with a clip, and check framing only when needed", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({ candidates: [
      cand({ clip: "01-one.mp4" }), cand({ n: 2, headline: "Two", needs_check: true }), cand({ n: 3, headline: "Three" })],
      clips: [clip()] }));
    render(<ClipWorkspace jobId="vid1" />);
    const one = await moments().findByRole("button", { name: /One/ });
    expect(within(one).getByText("Rendered")).toBeInTheDocument();
    expect(within(one).queryByText(/check framing/i)).toBeNull();
    expect(within(moments().getByRole("button", { name: /Two/ })).getByText("Check framing")).toBeInTheDocument();
    expect(moments().getByRole("button", { name: /Three/ })).not.toHaveTextContent(/check framing|rendered|approved/i);
    expect(screen.getAllByText(/check framing/i)).toHaveLength(1);
  });

  it("the phone plays the source range, and Rendered is off until the moment has a clip", async () => {
    render(<ClipWorkspace jobId="vid1" />);
    await moments().findByRole("button", { name: /One/ });
    const video = sourceVideo()!;
    expect(video.getAttribute("src")).toBe("/media/vid1/proxy.mp4");
    expect(video.currentTime).toBe(5);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();      // opening a job stays still
    expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
    expect(phoneView("Source")).toHaveTextContent("Source");
    expect(phoneView("Rendered")).toHaveAttribute("aria-pressed", "false");
    expect(phoneView("Rendered")).toHaveTextContent("Rendered");
    expect(phoneView("Rendered")).toBeDisabled();
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByRole("button", { name: /preview/i })).toBeNull();

    await userEvent.click(moments().getByRole("button", { name: /Two/ }));
    expect(sourceVideo()!.currentTime).toBe(15);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    sourceVideo()!.currentTime = 19.95;
    fireEvent.timeUpdate(sourceVideo()!);
    expect(vi.mocked(HTMLMediaElement.prototype.pause).mock.contexts).toContain(sourceVideo());
    expect(document.querySelector("video.proxy")).toBeNull();               // no separate strip
  });

  it("playing from past the moment's end doesn't stop at once; from inside it stops at the end", async () => {
    render(<ClipWorkspace jobId="vid1" />);
    await moments().findByRole("button", { name: /One/ });
    const video = sourceVideo()!;
    video.currentTime = 12;                                   // scrubbed past the end (9.9)
    fireEvent.play(video);
    video.currentTime = 12.3;
    fireEvent.timeUpdate(video);
    expect(HTMLMediaElement.prototype.pause).not.toHaveBeenCalled();
    video.currentTime = 6;                                    // back inside the moment
    fireEvent.play(video);
    video.currentTime = 9.95;
    fireEvent.timeUpdate(video);
    expect(vi.mocked(HTMLMediaElement.prototype.pause).mock.contexts).toContain(video);
  });

  it("a moment's rendered clip isn't shown unasked; the Rendered toggle shows it, and picking another moment goes back to the source", async () => {
    vi.mocked(api.getJob).mockResolvedValue(rendered());
    render(<ClipWorkspace jobId="vid1" />);
    await renderButton();
    expect(sourceVideo()).not.toBeNull();                                 // an old clip doesn't take over
    expect(phoneView("Rendered")).toBeEnabled();
    await userEvent.click(phoneView("Rendered"));
    expect(phoneView("Rendered")).toHaveAttribute("aria-pressed", "true");
    expect(phoneView("Source")).toHaveAttribute("aria-pressed", "false");
    expect(renderedVideo()?.getAttribute("src")).toBe("/media/vid1/clips/01-one.mp4?v=1-1");
    expect(sourceVideo()).toBeNull();
    await userEvent.click(phoneView("Source"));
    expect(sourceVideo()).not.toBeNull();
    expect(renderedVideo()).toBeNull();

    await userEvent.click(phoneView("Rendered"));
    await userEvent.click(moments().getByRole("button", { name: /Two/ }));
    expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
    expect(phoneView("Rendered")).toBeDisabled();                         // Two has no clip
    await userEvent.click(moments().getByRole("button", { name: /One/ }));
    expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
    expect(renderedVideo()).toBeNull();
  });

  it("⌘Z still undoes a moment's trim after looking at another moment", async () => {
    vi.mocked(api.patchCandidate).mockResolvedValue(cand());
    render(<ClipWorkspace jobId="vid1" />);
    await userEvent.click(await screen.findByRole("button", { name: /start −0\.5/i }));
    await waitFor(() => expect(api.patchCandidate).toHaveBeenCalledWith("vid1", 1, { start: 4.5 }));
    await userEvent.click(moments().getByRole("button", { name: /Two/ }));
    await userEvent.click(moments().getByRole("button", { name: /One/ }));
    fireEvent.keyDown(document.body, { key: "z", metaKey: true });
    await waitFor(() => expect(api.patchCandidate).toHaveBeenLastCalledWith("vid1", 1, { start: 5, end: 9.9 }));
  });

  it("a trim reloads the job and shows the new range", async () => {
    vi.mocked(api.patchCandidate).mockResolvedValue(cand({ start: 4.5 }));
    render(<ClipWorkspace jobId="vid1" />);
    const nudge = await screen.findByRole("button", { name: /start −0\.5/i });
    vi.mocked(api.getJob).mockResolvedValue(withOne({ start: 4.5, edited: true }));
    await userEvent.click(nudge);
    expect(await screen.findByText("0:04.5")).toBeInTheDocument();
    expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
    expect(sourceVideo()!.currentTime).toBe(4.5);
  });

  it("shows the moment's title, episode, range and length", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({ candidates: [
      cand({ start: 760.2, end: 778.4, finished_length: 18.2, bounds: { min_start: 700, max_end: 800 } })] }));
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByRole("heading", { name: "One" })).toBeInTheDocument();
    expect(screen.getByText("Episode · 12:40 → 12:58 · 18.2 s")).toBeInTheDocument();
  });

  it("has no Approve toggle, Preview button or bottom bar; P and A do nothing", async () => {
    render(<ClipWorkspace jobId="vid1" />);
    await renderButton();
    expect(screen.queryByRole("button", { name: /approve|preview|^more$|finished|^review$/i })).toBeNull();
    expect(screen.queryByRole("region", { name: "Render" })).toBeNull();
    await userEvent.keyboard("pa");
    expect(api.patchCandidate).not.toHaveBeenCalled();
    expect(api.render).not.toHaveBeenCalled();
  });

  describe("Render", () => {
    it("renders the selected moment, and tells the list", async () => {
      vi.mocked(api.render).mockResolvedValue({ queued: true });
      const heard = vi.fn();
      const stop = onChanged(heard);
      render(<ClipWorkspace jobId="vid1" />);
      const button = await renderButton();
      expect(button).toHaveClass("primary");
      expect(button).toHaveAccessibleName("Render");
      expect(button).toHaveTextContent("Render ⌘↵");
      expect(button).toHaveAttribute("title", "Render this clip (⌘↵)");
      await userEvent.click(button);
      expect(api.render).toHaveBeenCalledWith("vid1", 1);
      await waitFor(() => expect(heard).toHaveBeenCalled());
      expect(api.patchCandidate).not.toHaveBeenCalled();

      await userEvent.click(moments().getByRole("button", { name: /Two/ }));
      await userEvent.click(await renderButton());
      expect(api.render).toHaveBeenLastCalledWith("vid1", 2);
      expect(api.render).toHaveBeenCalledTimes(2);
      stop();
    });

    it("reloads when told something changed", async () => {
      render(<ClipWorkspace jobId="vid1" />);
      await renderButton();
      const calls = vi.mocked(api.getJob).mock.calls.length;
      act(() => notifyChanged());
      await waitFor(() => expect(vi.mocked(api.getJob).mock.calls.length).toBeGreaterThan(calls));
    });

    it("⌘Enter renders the selected moment, same as the button", async () => {
      vi.mocked(api.render).mockResolvedValue({ queued: true });
      render(<ClipWorkspace jobId="vid1" />);
      await renderButton();
      await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
      expect(api.render).toHaveBeenCalledWith("vid1", 1);
      await userEvent.keyboard("j");
      await screen.findByRole("heading", { name: "Two" });
      await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
      expect(api.render).toHaveBeenLastCalledWith("vid1", 2);
    });

    it("says Rendering… and waits while the moment renders; other moments can still be rendered", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_pending: true }));
      vi.mocked(api.render).mockResolvedValue({ queued: true });
      render(<ClipWorkspace jobId="vid1" />);
      expect(await renderButton()).toBeDisabled();
      expect(screen.getByRole("status")).toHaveTextContent(/^Rendering…$/);
      expect(moments().getByRole("button", { name: /One/ })).toHaveTextContent("Rendering…");
      await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
      expect(api.render).not.toHaveBeenCalled();
      // The moment can't be edited meanwhile either.
      expect(screen.getByRole("button", { name: /start −0\.5/i })).toBeDisabled();

      await userEvent.click(moments().getByRole("button", { name: /Two/ }));
      expect(screen.queryByRole("status")).toBeNull();
      expect(await renderButton()).toBeEnabled();
      await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
      expect(api.render).toHaveBeenCalledWith("vid1", 2);
    });

    it("pressing Render shows Rendering… once the server says the moment is pending", async () => {
      vi.mocked(api.render).mockResolvedValue({ queued: true });
      render(<ClipWorkspace jobId="vid1" />);
      const button = await renderButton();
      expect(screen.queryByRole("status")).toBeNull();
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_pending: true }));
      await userEvent.click(button);
      expect(await screen.findByRole("status")).toHaveTextContent("Rendering…");
      expect(button).toBeDisabled();
    });

    it("keeps checking on the job while a moment renders", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_pending: true }));
      render(<ClipWorkspace jobId="vid1" />);
      await screen.findByRole("status");
      const calls = vi.mocked(api.getJob).mock.calls.length;
      await waitFor(() => expect(vi.mocked(api.getJob).mock.calls.length).toBeGreaterThan(calls), { timeout: 4000 });
    });

    it("waits while the job is busy, and says what with", async () => {
      vi.mocked(api.getJob).mockResolvedValue(detail({ busy: true, editable: false,
        status: { state: "reframing", error: null, failed_step: null } }));
      render(<ClipWorkspace jobId="vid1" />);
      expect(await renderButton()).toBeDisabled();
      expect(screen.getByText("Busy: Framing…")).toBeInTheDocument();
      await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
      expect(api.render).not.toHaveBeenCalled();
    });

    it("waits while the moment's framing is redone", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ reframe_pending: true }));
      vi.mocked(api.render).mockResolvedValue({ queued: true });
      render(<ClipWorkspace jobId="vid1" />);
      expect(await renderButton()).toBeDisabled();
      expect(screen.getByText("Updating framing…")).toBeInTheDocument();
      expect(screen.queryByRole("status")).toBeNull();
      await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
      expect(api.render).not.toHaveBeenCalled();
      await userEvent.click(moments().getByRole("button", { name: /Two/ }));     // only that moment waits
      expect(await renderButton()).toBeEnabled();
    });

    it("⌘Enter does nothing while there's no moment to render", async () => {
      vi.mocked(api.getJob).mockResolvedValue(detail({ candidates: [] }));
      render(<ClipWorkspace jobId="vid1" />);
      await screen.findByText(/no moments were picked/i);
      expect(screen.queryByRole("button", { name: /^render/i })).toBeNull();
      await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
      expect(api.render).not.toHaveBeenCalled();
    });

    it("shows why Render was refused, and stays ready", async () => {
      vi.mocked(api.render).mockRejectedValue(new ApiError(409, "This moment can't render right now."));
      render(<ClipWorkspace jobId="vid1" />);
      await userEvent.click(await renderButton());
      expect(await screen.findByText("This moment can't render right now.")).toBeInTheDocument();
      expect(await renderButton()).toBeEnabled();
      await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
      expect(screen.queryByText("This moment can't render right now.")).toBeNull();
    });

    it("shows a moment's render error, on that moment only, and not while it renders again", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_error: "ffmpeg said no" }));
      render(<ClipWorkspace jobId="vid1" />);
      expect(await screen.findByRole("alert")).toHaveTextContent("ffmpeg said no");
      expect(await renderButton()).toBeEnabled();                            // it can be tried again
      await userEvent.click(moments().getByRole("button", { name: /Two/ }));
      expect(screen.queryByText("ffmpeg said no")).toBeNull();
      await userEvent.click(moments().getByRole("button", { name: /One/ }));
      expect(screen.getByText("ffmpeg said no")).toBeInTheDocument();
      serverNow(withOne({ render_error: "ffmpeg said no", render_pending: true }));
      await screen.findByRole("status");
      expect(screen.queryByText("ffmpeg said no")).toBeNull();
    });

    it("when the moment's render finishes, the phone switches to the rendered clip", async () => {
      vi.mocked(api.render).mockResolvedValue({ queued: true });
      render(<ClipWorkspace jobId="vid1" />);
      const button = await renderButton();
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_pending: true }));
      await userEvent.click(button);
      await screen.findByRole("status");
      expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
      expect(phoneView("Rendered")).toBeDisabled();

      serverNow(rendered());
      await waitFor(() => expect(phoneView("Rendered")).toHaveAttribute("aria-pressed", "true"));
      expect(renderedVideo()?.getAttribute("src")).toBe("/media/vid1/clips/01-one.mp4?v=1-1");
      expect(sourceVideo()).toBeNull();
      expect(screen.queryByRole("status")).toBeNull();
      expect(await renderButton()).toHaveAccessibleName("Render again");
      expect(await renderButton()).toBeEnabled();
      expect(within(moments().getByRole("button", { name: /One/ })).getByText("Rendered")).toBeInTheDocument();
    });

    it("a render already under way when the job was opened also ends on the rendered clip", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_pending: true }));
      render(<ClipWorkspace jobId="vid1" />);
      await screen.findByRole("status");
      // No nudge this time: the workspace's own polling notices.
      vi.mocked(api.getJob).mockResolvedValue(rendered());
      await waitFor(() => expect(phoneView("Rendered")).toHaveAttribute("aria-pressed", "true"), { timeout: 4000 });
      expect(renderedVideo()).not.toBeNull();
    });

    it("a render that fails stays on the source, with its error", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_pending: true }));
      render(<ClipWorkspace jobId="vid1" />);
      await screen.findByRole("status");
      serverNow(withOne({ render_error: "ffmpeg said no" }));
      expect(await screen.findByText("ffmpeg said no")).toBeInTheDocument();
      expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
      expect(phoneView("Rendered")).toBeDisabled();
      expect(await renderButton()).toHaveAccessibleName("Render");
    });

    it("another moment's render finishing doesn't take over the phone", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ render_pending: true }));
      render(<ClipWorkspace jobId="vid1" />);
      await screen.findByRole("status");
      await userEvent.click(moments().getByRole("button", { name: /Two/ }));
      serverNow(rendered());
      expect(await within(moments().getByRole("button", { name: /One/ })).findByText("Rendered")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Two" })).toBeInTheDocument();
      expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
      expect(sourceVideo()!.currentTime).toBe(15);
      // Going back to it shows the source too, with the clip one press away.
      await userEvent.click(moments().getByRole("button", { name: /One/ }));
      expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
      expect(phoneView("Rendered")).toBeEnabled();
    });

    it("Render again goes back to the source while it renders, then shows the new clip", async () => {
      vi.mocked(api.getJob).mockResolvedValue(rendered());
      vi.mocked(api.render).mockResolvedValue({ queued: true });
      render(<ClipWorkspace jobId="vid1" />);
      const button = await renderButton();
      expect(button).toHaveAccessibleName("Render again");
      expect(button).toHaveTextContent("Render again ⌘↵");
      await userEvent.click(phoneView("Rendered"));
      vi.mocked(api.getJob).mockResolvedValue(withOne({ clip: "01-one.mp4", render_pending: true }, [clip()]));
      await userEvent.click(button);
      expect(api.render).toHaveBeenCalledWith("vid1", 1);
      await screen.findByRole("status");
      expect(phoneView("Source")).toHaveAttribute("aria-pressed", "true");
      expect(button).toBeDisabled();
      expect(screen.queryByRole("button", { name: /mark posted/i })).toBeNull();   // the old clip's actions wait

      serverNow(rendered({ version: "2-2" }));
      await waitFor(() => expect(renderedVideo()?.getAttribute("src")).toBe("/media/vid1/clips/01-one.mp4?v=2-2"));
      expect(phoneView("Rendered")).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "Mark posted" })).toBeInTheDocument();
    });
  });

  describe("a rendered moment's clip", () => {
    it("has Mark posted, Copy caption and Show in Finder under the moment; a moment without a clip has none", async () => {
      vi.mocked(api.getJob).mockResolvedValue(rendered());
      vi.mocked(api.setPosted).mockResolvedValue(clip({ posted_at: "2026-09-25T10:00:00Z" }));
      vi.mocked(api.reveal).mockResolvedValue({ revealed: true });
      render(<ClipWorkspace jobId="vid1" />);
      const mark = await screen.findByRole("button", { name: "Mark posted" });
      expect(mark).toHaveAttribute("aria-pressed", "false");
      expect(screen.getByRole("button", { name: "Copy caption" })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Show in Finder" }));
      expect(api.reveal).toHaveBeenCalledWith("vid1", "01-one.mp4");

      vi.mocked(api.getJob).mockResolvedValue(rendered({ posted_at: "2026-09-25T10:00:00Z" }));
      await userEvent.click(mark);
      expect(api.setPosted).toHaveBeenCalledWith("vid1", "01-one.mp4", true);
      // Marking it tells everyone, this workspace included: it reloads and shows Posted.
      expect(await screen.findByRole("button", { name: "Posted" })).toHaveAttribute("aria-pressed", "true");

      await userEvent.click(moments().getByRole("button", { name: /Two/ }));
      expect(screen.queryByRole("button", { name: /^(mark posted|posted|copy caption|show in finder)$/i })).toBeNull();
    });

    it("a moment whose clip file isn't among the job's clips is treated as not rendered", async () => {
      vi.mocked(api.getJob).mockResolvedValue(withOne({ clip: "01-one.mp4" }, []));
      render(<ClipWorkspace jobId="vid1" />);
      expect(await renderButton()).toHaveAccessibleName("Render");
      expect(phoneView("Rendered")).toBeDisabled();
      expect(screen.queryByRole("button", { name: "Mark posted" })).toBeNull();
    });
  });

  it("explains an empty result instead of showing a blank list", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({ candidates: [] }));
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByText(/no moments were picked/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Episode" })).toBeInTheDocument();
    expect(screen.getByText("No moment picked yet.")).toBeInTheDocument();
  });

  it("shows no empty-result message while the job is still processing", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({
      candidates: [], busy: true, editable: false,
      status: { state: "transcribing", error: null, failed_step: null } }));
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByText("Busy: Transcribing…")).toBeInTheDocument();
    expect(screen.queryByText(/no moments were picked/i)).not.toBeInTheDocument();
  });

  it("shows a failed framing update on that clip", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({ candidates: [cand({ reframe_error: "no faces decoded" })] }));
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByText(/no faces decoded/)).toBeInTheDocument();
  });

  it("keeps the page and says so when the server can't be reached, then recovers", async () => {
    render(<ClipWorkspace jobId="vid1" />);
    await moments().findByRole("button", { name: /One/ });
    vi.mocked(api.getJob).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    act(() => notifyChanged());                              // reloads
    expect(await screen.findByText(/can't reach clipper/i)).toBeInTheDocument();
    expect(moments().getByRole("button", { name: /One/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/can't reach clipper/i)).not.toBeInTheDocument(),
                  { timeout: 4000 });
  });

  it("a job that doesn't exist gets an error page: what happened and the way back", async () => {
    vi.mocked(api.getJob).mockRejectedValue(new ApiError(404, "No job called 'gone'."));
    render(<ClipWorkspace jobId="gone" />);
    expect(await screen.findByRole("heading", { name: "This job isn't here" })).toBeInTheDocument();
    const page = within(screen.getByRole("alert"));
    expect(page.getByText("It may have been deleted, or the link is wrong.")).toBeInTheDocument();
    expect(page.getByRole("link", { name: "All clip jobs" })).toHaveAttribute("href", "#/");
    expect(page.queryByRole("button", { name: "Try again" })).toBeNull();     // trying again won't bring it back
  });

  it("a job the server can't load says why, how to fix it, and offers Try again", async () => {
    vi.mocked(api.getJob).mockRejectedValueOnce(new ApiError(500, "Clipper hit an unexpected error: KeyError: 'campaign'"))
      .mockResolvedValue(detail());
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByRole("heading", { name: "Couldn't open this job" })).toBeInTheDocument();
    const page = within(screen.getByRole("alert"));
    expect(page.getByText(/^How to fix:/).closest("p")).toHaveTextContent(/the terminal running Clipper/);
    expect(page.getByText("Details")).toBeInTheDocument();
    await userEvent.click(page.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: /^Render/ })).toBeInTheDocument();
  });

  it("a failed job shows its error with Retry, and a refused retry shows why", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({
      status: { state: "failed", error: "boom", failed_step: "render" } }));
    vi.mocked(api.retry).mockRejectedValue(new Error("Only failed jobs can be retried."));
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.queryByText(/^Busy:/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry from render" }));
    expect(api.retry).toHaveBeenCalledWith("vid1");
    expect(await screen.findByText("Only failed jobs can be retried.")).toBeInTheDocument();
  });

  it("shows a failed job's error with a retry, which tells the list", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({
      status: { state: "failed", error: "pick failed: overloaded", failed_step: "pick" },
      editable: false,
    }));
    vi.mocked(api.retry).mockResolvedValue({ queued: true });
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByText("pick failed: overloaded")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /retry from pick/i }));
    expect(api.retry).toHaveBeenCalledWith("vid1");
    await waitFor(() => expect(heard).toHaveBeenCalled());
    stop();
  });

  it("asks before picking again over edits", async () => {
    vi.mocked(api.getJob).mockResolvedValue(detail({ candidates: [cand({ edited: true })] }));
    vi.mocked(api.repick).mockResolvedValue({ queued: true });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ClipWorkspace jobId="vid1" />);
    await userEvent.click(await pickAgain());
    expect(confirm).toHaveBeenCalledWith("Picking again replaces every moment, including your edits. Continue?");
    expect(api.repick).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await userEvent.click(await pickAgain());
    expect(api.repick).toHaveBeenCalledWith("vid1", true);
    confirm.mockRestore();
  });

  it("the question says rendered clips stay, when there are some", async () => {
    vi.mocked(api.getJob).mockResolvedValue(withOne({ edited: true, clip: "01-one.mp4" }, [clip()]));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ClipWorkspace jobId="vid1" />);
    await userEvent.click(await pickAgain());
    expect(confirm).toHaveBeenCalledWith(
      "Picking again replaces every moment, including your edits. Clips you already rendered stay on the Rendered page. Continue?");
    expect(api.repick).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("Pick again sits in the workspace's header, and not while the job is busy", async () => {
    const { unmount } = render(<ClipWorkspace jobId="vid1" />);
    const button = await pickAgain();
    expect(button).toBeEnabled();
    expect(button).toHaveClass("ghost");
    expect(button.closest(".ws-head")).not.toBeNull();
    expect(screen.queryByRole("menuitem")).toBeNull();
    unmount();
    vi.mocked(api.getJob).mockResolvedValue(detail({ busy: true }));
    render(<ClipWorkspace jobId="vid1" />);
    expect(await pickAgain()).toBeDisabled();
  });

  it("picks again without asking when nothing is edited, even with clips rendered, and tells the list", async () => {
    vi.mocked(api.getJob).mockResolvedValue(rendered());
    vi.mocked(api.repick).mockResolvedValue({ queued: true });
    const confirm = vi.spyOn(window, "confirm");
    const heard = vi.fn();
    const stop = onChanged(heard);
    render(<ClipWorkspace jobId="vid1" />);
    await userEvent.click(await pickAgain());
    expect(confirm).not.toHaveBeenCalled();
    expect(api.repick).toHaveBeenCalledWith("vid1", false);
    await waitFor(() => expect(heard).toHaveBeenCalled());
    stop();
    confirm.mockRestore();
  });

  it("shows why picking again was refused", async () => {
    vi.mocked(api.repick).mockRejectedValue(new ApiError(409, "This job is busy."));
    render(<ClipWorkspace jobId="vid1" />);
    await userEvent.click(await pickAgain());
    expect(await screen.findByText("This job is busy.")).toBeInTheDocument();
  });

  it("shows skeletons, not Loading…, while the job first loads", () => {
    vi.mocked(api.getJob).mockReturnValue(new Promise(() => {}));
    render(<ClipWorkspace jobId="vid1" />);
    expect(screen.queryByText("Loading…")).toBeNull();
    expect(document.querySelectorAll(".ws-frame .skeleton").length).toBeGreaterThan(0);
  });

  it("opening a job while the server is down says so", async () => {
    vi.mocked(api.getJob).mockRejectedValue(new TypeError("Failed to fetch"));
    render(<ClipWorkspace jobId="vid1" />);
    expect(await screen.findByRole("heading", { name: "Can't reach Clipper" })).toBeInTheDocument();
    expect(screen.getByText(/^How to fix:/).closest("p")).toHaveTextContent("start Clipper again (./start)");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
