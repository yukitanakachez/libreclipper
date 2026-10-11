import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import App from "./App";
import "./styles.css";   // vite.config lets Vitest load this one stylesheet into jsdom
import { cand, detail, job, renderedClip, settings } from "./test-fixtures";

vi.mock("./api", async () => {
  const real = await vi.importActual<typeof import("./api")>("./api");
  return { ...real, api: { ...real.api, listJobs: vi.fn(), listCampaigns: vi.fn(), getJob: vi.fn(),
                            patchCandidate: vi.fn(), saveWordFixes: vi.fn(), render: vi.fn(),
                            listClips: vi.fn(), setPosted: vi.fn(), revealConfig: vi.fn(),
                            getSettings: vi.fn(), setupChecks: vi.fn() } };
});

beforeEach(() => {
  vi.mocked(api.listJobs).mockResolvedValue([job()]);
  vi.mocked(api.listCampaigns).mockResolvedValue([]);
  vi.mocked(api.getJob).mockResolvedValue(detail());
  vi.mocked(api.patchCandidate).mockResolvedValue(cand());
  vi.mocked(api.listClips).mockResolvedValue([renderedClip()]);
  vi.mocked(api.getSettings).mockResolvedValue(settings());
  vi.mocked(api.setupChecks).mockResolvedValue([]);
});

const goTo = (hash: string) =>
  act(() => { window.location.hash = hash; window.dispatchEvent(new HashChangeEvent("hashchange")); });

describe("App", () => {
  it("opens on the board: Next up, then every clip job", async () => {
    window.location.hash = "#/";
    render(<App />);
    const board = screen.getByRole("navigation", { name: /clip jobs/i });
    expect(await within(board).findByRole("link", { name: /episode 1/i })).toHaveAttribute("href", "#/clips/vid1");
    expect(await screen.findByText(/next up/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open/i })).toHaveAttribute("href", "#/clips/vid1");
    expect(screen.queryByRole("navigation", { name: /primary/i })).toBeNull();      // no sidebar
    expect(screen.queryByRole("navigation", { name: /moments/i })).toBeNull();
  });

  it("an open clip job shows its moments in the list column, with a way back", async () => {
    window.location.hash = "#/clips/vid1";
    render(<App />);
    const list = await screen.findByRole("navigation", { name: /moments/i });
    expect(await within(list).findByRole("button", { name: /One/ })).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: /all clip jobs/i })).toHaveAttribute("href", "#/");
    expect(screen.queryByRole("navigation", { name: /clip jobs/i })).toBeNull();
    expect(screen.queryByText(/next up/i)).toBeNull();
    expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument();
  });

  it("links to the sections that are gone open the board", async () => {
    for (const hash of ["#/stories/r-abc123", "#/posting", "#/photos"]) {
      window.location.hash = hash;
      const { unmount } = render(<App />);
      expect(await screen.findByRole("link", { name: /episode 1/i })).toBeInTheDocument();
      expect(screen.getByRole("navigation", { name: /clip jobs/i })).toBeInTheDocument();
      expect(api.getJob).not.toHaveBeenCalled();
      unmount();
    }
  });

  it("an old review link still opens its clip job", async () => {
    window.location.hash = "#/jobs/vid1";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "One" })).toBeInTheDocument();
    expect(api.getJob).toHaveBeenCalledWith("vid1");
  });

  it("the page area is the main landmark, reached by a skip link that comes first in tab order", async () => {
    window.location.hash = "#/";
    render(<App />);
    await screen.findByRole("link", { name: /episode 1/i });
    const main = screen.getByRole("main");
    expect(main).toContainElement(screen.getByText(/next up/i));
    expect(main).toContainElement(screen.getByRole("navigation", { name: /clip jobs/i }));
    await userEvent.tab();
    const skip = screen.getByRole("link", { name: "Skip to workspace" });
    expect(skip).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(document.activeElement).toHaveClass("next-up");              // the workspace in the main
    expect(main).toContainElement(document.activeElement as HTMLElement);
    expect(window.location.hash).toBe("#/");
  });

  it("the skip link lands on an open clip job's workspace", async () => {
    window.location.hash = "#/clips/vid1";
    render(<App />);
    await screen.findByRole("heading", { name: "One" });
    await userEvent.click(screen.getByRole("link", { name: "Skip to workspace" }));
    expect(document.activeElement).toHaveClass("workspace");
  });

  it("the skip link falls back to the main when there is no workspace: a job that doesn't exist", async () => {
    vi.mocked(api.getJob).mockRejectedValue(new ApiError(404, "No job called 'gone'."));
    window.location.hash = "#/clips/gone";
    render(<App />);
    const main = await screen.findByRole("main");
    await screen.findByRole("heading", { name: "This job isn't here" });
    await userEvent.click(screen.getByRole("link", { name: "Skip to workspace" }));
    expect(main).toHaveFocus();
  });

  it("the window title follows the open job", async () => {
    window.location.hash = "#/";
    const { unmount } = render(<App />);
    await screen.findByRole("link", { name: /episode 1/i });
    expect(document.title).toBe("Clipper");
    goTo("#/clips/vid1");
    await screen.findByRole("heading", { name: "One" });
    await waitFor(() => expect(document.title).toBe("Episode 1 · Clipper"));
    goTo("#/");
    await screen.findByRole("navigation", { name: /clip jobs/i });
    expect(document.title).toBe("Clipper");
    unmount();
  });

  it("#/rendered opens the Rendered page, named in the window title, with nothing else in the main", async () => {
    window.location.hash = "#/rendered";
    const { unmount } = render(<App />);
    expect(await screen.findByRole("heading", { name: "Rendered clips" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Episode 1" })).toHaveAttribute("href", "#/clips/vid1");
    expect(api.listClips).toHaveBeenCalled();
    expect(api.getJob).not.toHaveBeenCalled();
    expect(screen.queryByRole("navigation", { name: /clip jobs|moments/i })).toBeNull();
    expect(screen.queryByText(/next up/i)).toBeNull();
    expect(document.title).toBe("Rendered clips · Clipper");
    goTo("#/");
    await screen.findByRole("navigation", { name: /clip jobs/i });
    expect(screen.queryByRole("heading", { name: "Rendered clips" })).toBeNull();
    expect(document.title).toBe("Clipper");
    unmount();
  });

  it("the skip link lands on the Rendered page", async () => {
    window.location.hash = "#/rendered";
    render(<App />);
    await screen.findByRole("heading", { name: "Rendered clips" });
    await userEvent.click(screen.getByRole("link", { name: "Skip to workspace" }));
    expect(document.activeElement).toHaveClass("rendered-page");
  });

  it("New opens the New clip job sheet", async () => {
    window.location.hash = "#/";
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /^new/i }));
    expect(await screen.findByRole("dialog", { name: "New clip job" })).toBeInTheDocument();
    expect(screen.getByLabelText(/video file/i)).toBeInTheDocument();
    expect(screen.queryByRole("tab")).toBeNull();
  });

  it("with no jobs yet, the board's own New clip job button opens the same sheet", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([]);
    window.location.hash = "#/";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Turn a video into clips" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New clip job" }));
    expect(await screen.findByRole("dialog", { name: "New clip job" })).toBeInTheDocument();
  });

  it("sits on the gradient backdrop, which is decoration only; no glass", async () => {
    window.location.hash = "#/";
    render(<App />);
    expect(await screen.findByRole("link", { name: /episode 1/i })).toBeInTheDocument();
    expect(document.querySelector(".glass")).toBeNull();
    expect(document.querySelector(".backdrop")).toHaveAttribute("aria-hidden", "true");
    expect(getComputedStyle(document.documentElement).getPropertyValue("--bg").trim()).toBe("#ffffff");
  });

  it("N opens the New sheet, same as the button", async () => {
    window.location.hash = "#/";
    render(<App />);
    await screen.findByRole("link", { name: /episode 1/i });
    await userEvent.keyboard("n");
    expect(await screen.findByLabelText(/video file/i)).toBeInTheDocument();
  });

  it("N opens the New sheet from an open job too", async () => {
    window.location.hash = "#/clips/vid1";
    render(<App />);
    await screen.findByRole("heading", { name: "One" });
    await userEvent.keyboard("n");
    expect(await screen.findByRole("dialog", { name: "New clip job" })).toBeInTheDocument();
  });

  it("New shows N as its shortcut", async () => {
    window.location.hash = "#/";
    render(<App />);
    const button = await screen.findByRole("button", { name: /^new/i });
    expect(within(button).getByText("N")).toHaveClass("kbd");
  });

  it("J and K move focus between the board's cards", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job(), job({ id: "vid2", title: "Episode 2" })]);
    window.location.hash = "#/";
    render(<App />);
    const board = screen.getByRole("navigation", { name: /clip jobs/i });
    const first = await within(board).findByRole("link", { name: /episode 1/i });
    await userEvent.keyboard("j");
    expect(first).toHaveFocus();
    await userEvent.keyboard("j");
    expect(within(board).getByRole("link", { name: /episode 2/i })).toHaveFocus();
    await userEvent.keyboard("k");
    expect(first).toHaveFocus();
    expect(window.location.hash).toBe("#/");
  });

  it("typing j/k/n in the transcript's spelling box fires no shortcut", async () => {
    window.location.hash = "#/clips/vid1";
    render(<App />);
    await userEvent.dblClick(await screen.findByRole("option", { name: "w11." }));
    const input = await screen.findByRole("textbox", { name: /fix spelling/i });
    await userEvent.clear(input);
    await userEvent.type(input, "jkn");
    expect(input).toHaveValue("jkn");
    expect(api.render).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument();     // J didn't move on
    expect(window.location.hash).toBe("#/clips/vid1");
  });

  it("j/k/n fire no shortcut while the New sheet is open", async () => {
    window.location.hash = "#/";
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^new/i }));
    const field = await screen.findByLabelText(/video file/i);
    await userEvent.keyboard("jkn");
    expect(field).toHaveFocus();                                                  // J/K didn't move it
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(window.location.hash).toBe("#/");
  });

  it("⌘↵ in an open job renders the selected moment", async () => {
    vi.mocked(api.render).mockResolvedValue({ queued: true });
    window.location.hash = "#/clips/vid1";
    render(<App />);
    await screen.findByRole("button", { name: /^render$/i });
    await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
    expect(api.render).toHaveBeenCalledWith("vid1", 1);
    await userEvent.keyboard("j");
    await screen.findByRole("heading", { name: "Two" });
    await userEvent.keyboard("{Meta>}{Enter}{/Meta}");
    expect(api.render).toHaveBeenLastCalledWith("vid1", 2);
  });

  it("? opens the keyboard shortcuts list", async () => {
    window.location.hash = "#/";
    render(<App />);
    await screen.findByRole("link", { name: /episode 1/i });
    await userEvent.keyboard("?");
    const dialog = await screen.findByRole("dialog", { name: /keyboard shortcuts/i });
    expect(within(dialog).getByText(/next \/ previous job or moment/i)).toBeInTheDocument();
    expect(within(dialog).getByText("Render this clip")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shortcuts are ignored while the New sheet is open", async () => {
    window.location.hash = "#/";
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /^new/i }));
    await screen.findByRole("dialog", { name: "New clip job" });
    await userEvent.keyboard("?");
    expect(screen.queryByRole("dialog", { name: /keyboard shortcuts/i })).toBeNull();
  });
});

describe("App top bar", () => {
  it("names Clipper, with Rendered, the Inbox, Settings, the shortcut list and New on the right", async () => {
    window.location.hash = "#/";
    render(<App />);
    const top = screen.getByRole("banner");
    await screen.findByRole("link", { name: /episode 1/i });
    expect(top.querySelector(".crumb")).toHaveTextContent(/^Clipper$/);
    expect(within(top).getByRole("link", { name: "Clipper" })).toHaveAttribute("href", "#/");
    expect(within(top).getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent))
      .toEqual([expect.stringMatching(/^Inbox/), "Keyboard shortcuts", "New N"]);
    expect(within(top).getByRole("link", { name: "Settings" })).toHaveAttribute("href", "#/settings");
    expect(within(top).queryByRole("button", { name: "Channel" })).toBeNull();        // no avatar menu
    // Rendered is a link, ahead of the buttons.
    const rendered = within(top).getByRole("link", { name: "Rendered" });
    expect(rendered).toHaveAttribute("href", "#/rendered");
    expect(rendered.compareDocumentPosition(within(top).getByRole("button", { name: /^Inbox/ }))
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("the Rendered link counts the rendered clips not posted yet, across every job", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([
      job({ clips: 1 }),                                                             // still in review
      job({ id: "vid2", title: "Episode 2", state: "done", clips: 3, posted: 1 }),
      job({ id: "vid3", title: "Episode 3", state: "done", clips: 2, posted: 2 }),
    ]);
    window.location.hash = "#/";
    render(<App />);
    const top = within(screen.getByRole("banner"));
    const link = top.getByRole("link", { name: /^Rendered/ });
    expect(link.querySelector(".count")).toBeNull();                                // nothing loaded yet
    await waitFor(() => expect(link.querySelector(".count")).toHaveTextContent(/^3$/));
    expect(link).toHaveAttribute("title", "3 rendered clips not posted yet");
    expect(link).not.toHaveAttribute("aria-current");
  });

  it("the Rendered link has no count when nothing waits, and says 1 clip for one", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job({ id: "vid2", state: "done", clips: 2, posted: 2 })]);
    window.location.hash = "#/";
    const { unmount } = render(<App />);
    await screen.findByRole("navigation", { name: /clip jobs/i });
    await screen.findByText(/all caught up/i);
    const link = within(screen.getByRole("banner")).getByRole("link", { name: "Rendered" });
    expect(link.querySelector(".count")).toBeNull();
    expect(link).toHaveAttribute("title", "Every rendered clip");
    unmount();

    vi.mocked(api.listJobs).mockResolvedValue([job({ id: "vid2", state: "done", clips: 2, posted: 1 })]);
    render(<App />);
    await waitFor(() => expect(within(screen.getByRole("banner")).getByRole("link", { name: /^Rendered/ }))
      .toHaveAttribute("title", "1 rendered clip not posted yet"));
  });

  it("the Rendered link opens the Rendered page, is current there, and the page follows Clipper", async () => {
    window.location.hash = "#/";
    render(<App />);
    const top = screen.getByRole("banner");
    await screen.findByRole("navigation", { name: /clip jobs/i });
    await userEvent.click(within(top).getByRole("link", { name: /^Rendered/ }));
    expect(window.location.hash).toBe("#/rendered");
    expect(await screen.findByRole("heading", { name: "Rendered clips" })).toBeInTheDocument();
    expect(within(top).getByRole("link", { name: /^Rendered/ })).toHaveAttribute("aria-current", "page");
    expect(top.querySelector(".crumb")).toHaveTextContent(/^Clipper\/Rendered clips$/);
    await userEvent.click(within(top).getByRole("link", { name: "Clipper" }));
    expect(await screen.findByRole("navigation", { name: /clip jobs/i })).toBeInTheDocument();
    expect(within(top).getByRole("link", { name: /^Rendered/ })).not.toHaveAttribute("aria-current");
  });

  it("marking a clip posted on the Rendered page brings the top bar's count down", async () => {
    vi.mocked(api.listJobs).mockResolvedValue([job({ state: "done", clips: 1 })]);
    vi.mocked(api.setPosted).mockResolvedValue(renderedClip({ posted_at: "2026-09-25T10:00:00Z" }));
    window.location.hash = "#/rendered";
    render(<App />);
    const link = within(screen.getByRole("banner")).getByRole("link", { name: /^Rendered/ });
    await waitFor(() => expect(link.querySelector(".count")).toHaveTextContent(/^1$/));
    vi.mocked(api.listJobs).mockResolvedValue([job({ state: "done", clips: 1, posted: 1 })]);
    await userEvent.click(await screen.findByRole("button", { name: "Mark posted" }));
    expect(api.setPosted).toHaveBeenCalledWith("vid1", "01-one.mp4", true);
    await waitFor(() => expect(link.querySelector(".count")).toBeNull());
  });

  it("an open job's title follows Clipper, which leads back to the board", async () => {
    window.location.hash = "#/clips/vid1";
    render(<App />);
    const top = screen.getByRole("banner");
    await within(top).findByText("Episode 1");
    expect(top.querySelector(".crumb")).toHaveTextContent(/^Clipper\/Episode 1$/);
    await userEvent.click(within(top).getByRole("link", { name: "Clipper" }));
    expect(window.location.hash).toBe("#/");
    expect(await screen.findByRole("navigation", { name: /clip jobs/i })).toBeInTheDocument();
    expect(top.querySelector(".crumb")).toHaveTextContent(/^Clipper$/);
  });

  it("the Keyboard shortcuts button opens the same list as ?", async () => {
    window.location.hash = "#/";
    render(<App />);
    await userEvent.click(within(screen.getByRole("banner")).getByRole("button", { name: "Keyboard shortcuts" }));
    const dialog = await screen.findByRole("dialog", { name: /keyboard shortcuts/i });
    expect(within(dialog).getByText("Undo trim")).toBeInTheDocument();
  });

  it("the gear opens Settings, where Show config.yaml reveals the file or says why it can't", async () => {
    vi.mocked(api.revealConfig).mockResolvedValueOnce({ revealed: true })
      .mockRejectedValueOnce(new ApiError(404, "There is no config.yaml yet."));
    window.location.hash = "#/";
    render(<App />);
    await userEvent.click(within(screen.getByRole("banner")).getByRole("link", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(document.title).toBe("Settings · Clipper");
    expect(within(screen.getByRole("banner")).getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");
    const button = screen.getByRole("button", { name: "Show config.yaml" });
    await userEvent.click(button);
    expect(api.revealConfig).toHaveBeenCalledTimes(1);
    await userEvent.click(button);
    expect(await screen.findByText("There is no config.yaml yet.")).toBeInTheDocument();
  });

  it("with no AI provider ready, the board gives way to setup; a job link still opens", async () => {
    vi.mocked(api.getSettings).mockResolvedValue(settings({}, false));
    window.location.hash = "#/";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Set up Clipper" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Clip jobs" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Done" })).toBeNull();      // nothing chosen yet
    await goTo("#/clips/vid1");
    expect(await screen.findByRole("navigation", { name: "Moments" })).toBeInTheDocument();
  });

  it("the Inbox counts what the overview already polls: a job to review and a rendered one", async () => {
    localStorage.removeItem("clipper.inbox.read");
    vi.mocked(api.listJobs).mockResolvedValue([job(), job({ id: "vid2", title: "Episode 2", state: "done", clips: 2 }),
                                               job({ id: "vid3", title: "Episode 3", state: "transcribing", busy: true })]);
    window.location.hash = "#/";
    render(<App />);
    const inbox = await screen.findByRole("button", { name: "Inbox, 2 unread" });
    await userEvent.click(inbox);
    const pop = screen.getByRole("dialog", { name: "Inbox" });
    expect(within(pop).getByRole("link", { name: /ready for review: episode 1/i }))
      .toHaveAttribute("href", "#/clips/vid1");
    expect(within(pop).getByRole("link", { name: /rendered: episode 2 2 clips/i })).toHaveAttribute("href", "#/clips/vid2");
    await userEvent.click(within(pop).getByRole("link", { name: /rendered: episode 2/i }));
    expect(window.location.hash).toBe("#/clips/vid2");
    expect(screen.getByRole("button", { name: "Inbox, 1 unread" })).toBeInTheDocument();
  });
});
