import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { renderedClip } from "../test-fixtures";
import RenderedPage from "./RenderedPage";

vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { listClips: vi.fn(), setPosted: vi.fn(), reveal: vi.fn() } };
});

const before = (ms: number) => new Date(Date.now() - ms).toISOString();
const HOUR = 3600_000;
const DAY = 24 * HOUR;

/** Two clips waiting to be posted (from two jobs) and one that is out. */
const three = () => [
  renderedClip({ headline: "One", rendered_at: before(5 * 60_000) }),
  renderedClip({ file: "02-two.mp4", headline: "Two", version: "2-2", rendered_at: before(3 * HOUR),
                 posted_at: before(30_000) }),
  renderedClip({ job_id: "vid 2", job_title: "Episode 2", file: "01 three.mp4", headline: "Three", version: "3-3",
                 rendered_at: before(2 * DAY) }),
];

beforeEach(() => {
  vi.mocked(api.listClips).mockResolvedValue(three());
});

const tab = (name: "Not posted" | "Posted" | "All") =>
  within(screen.getByRole("tablist", { name: "Show" })).getByRole("tab", { name: new RegExp(`^${name}`) });
const cards = () => screen.queryAllByRole("listitem");
const titles = () => cards().map((c) => c.querySelector("strong")!.textContent);
const card = (title: string) => screen.getByText(title, { selector: "strong" }).closest("li")!;

describe("RenderedPage", () => {
  it("opens on the clips not posted yet, with a count on each filter", async () => {
    render(<RenderedPage />);
    expect(screen.getByRole("heading", { name: "Rendered clips" })).toBeInTheDocument();
    await waitFor(() => expect(titles()).toEqual(["One", "Three"]));
    expect(tab("Not posted")).toHaveAttribute("aria-selected", "true");
    expect(tab("Posted")).toHaveAttribute("aria-selected", "false");
    expect(tab("All")).toHaveAttribute("aria-selected", "false");
    expect(tab("Not posted")).toHaveTextContent(/^Not posted2$/);
    expect(tab("Posted")).toHaveTextContent(/^Posted1$/);
    expect(tab("All")).toHaveTextContent(/^All3$/);
    expect(screen.getAllByRole("tab")).toHaveLength(3);
  });

  it("Posted shows what is out, All shows everything in the order it came", async () => {
    render(<RenderedPage />);
    await waitFor(() => expect(titles()).toEqual(["One", "Three"]));
    await userEvent.click(tab("Posted"));
    expect(titles()).toEqual(["Two"]);
    expect(tab("Posted")).toHaveAttribute("aria-selected", "true");
    expect(tab("Not posted")).toHaveAttribute("aria-selected", "false");
    await userEvent.click(tab("All"));
    expect(titles()).toEqual(["One", "Two", "Three"]);
    expect(tab("All")).toHaveAttribute("aria-selected", "true");
    await userEvent.click(tab("Not posted"));
    expect(titles()).toEqual(["One", "Three"]);
    expect(api.listClips).toHaveBeenCalledTimes(1);                       // filtering asks the server nothing
  });

  it("a card plays the clip, names it, links to its job and says where it stands", async () => {
    render(<RenderedPage />);
    await waitFor(() => expect(cards()).toHaveLength(2));
    const three = card("Three");
    expect(three.querySelector("video")).toHaveAttribute("src", "/media/vid%202/clips/01%20three.mp4?v=3-3");
    expect(three.querySelector("video")).toHaveAttribute("controls");
    expect(within(three).getByRole("link", { name: "Episode 2" })).toHaveAttribute("href", "#/clips/vid%202");
    expect(within(three).getByText("Not posted · rendered 2 d ago")).toBeInTheDocument();
    expect(three).not.toHaveClass("posted");
    expect(within(three).getByRole("button", { name: "Mark posted" })).toHaveAttribute("aria-pressed", "false");
    expect(within(three).getByRole("button", { name: "Copy caption" })).toBeInTheDocument();
    expect(within(three).getByRole("button", { name: "Show in Finder" })).toBeInTheDocument();
    expect(within(card("One")).getByText("Not posted · rendered 5 min ago")).toBeInTheDocument();
    expect(within(card("One")).getByRole("link", { name: "Episode 1" })).toHaveAttribute("href", "#/clips/vid1");

    await userEvent.click(tab("Posted"));
    const two = card("Two");
    expect(two).toHaveClass("posted");
    expect(within(two).getByText("Posted just now")).toHaveClass("ok");
    expect(two).toHaveTextContent("Posted just now · rendered 3 h ago");
    expect(within(two).getByRole("button", { name: "Posted" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a clip without a headline goes by its file name, made readable; a job without a title by its id", async () => {
    vi.mocked(api.listClips).mockResolvedValue([
      renderedClip({ file: "01-the-weekly-kill-list.mp4", headline: null, caption: "A caption line\n#pod", job_title: null }),
      renderedClip({ file: "12-two.mp4", headline: null, caption: "" }),
      renderedClip({ file: "untitled.mov", headline: null }),
    ]);
    render(<RenderedPage />);
    await waitFor(() => expect(titles()).toEqual(["The weekly kill list", "Two", "Untitled.mov"]));
    expect(within(card("The weekly kill list")).getByRole("link", { name: "vid1" })).toHaveAttribute("href", "#/clips/vid1");
    expect(card("The weekly kill list").querySelector("video"))
      .toHaveAttribute("src", "/media/vid1/clips/01-the-weekly-kill-list.mp4?v=1-1");
  });

  it("marking a clip posted asks the server, then the reloaded list moves it to Posted", async () => {
    vi.mocked(api.setPosted).mockResolvedValue(renderedClip({ posted_at: before(0) }));
    render(<RenderedPage />);
    await waitFor(() => expect(cards()).toHaveLength(2));
    const [one, two, last] = three();
    vi.mocked(api.listClips).mockResolvedValue([one, two, { ...last, posted_at: before(0) }]);
    await userEvent.click(within(card("Three")).getByRole("button", { name: "Mark posted" }));
    expect(api.setPosted).toHaveBeenCalledWith("vid 2", "01 three.mp4", true);
    await waitFor(() => expect(titles()).toEqual(["One"]));
    expect(tab("Not posted")).toHaveTextContent(/^Not posted1$/);
    expect(tab("Posted")).toHaveTextContent(/^Posted2$/);
    expect(tab("All")).toHaveTextContent(/^All3$/);
    await userEvent.click(tab("Posted"));
    expect(titles()).toEqual(["Two", "Three"]);
  });

  it("taking Posted back asks the server too, and the clip returns to Not posted", async () => {
    vi.mocked(api.setPosted).mockResolvedValue(renderedClip());
    render(<RenderedPage />);
    await waitFor(() => expect(cards()).toHaveLength(2));
    await userEvent.click(tab("Posted"));
    vi.mocked(api.listClips).mockResolvedValue(three().map((c) => ({ ...c, posted_at: null })));
    await userEvent.click(within(card("Two")).getByRole("button", { name: "Posted" }));
    expect(api.setPosted).toHaveBeenCalledWith("vid1", "02-two.mp4", false);
    expect(await screen.findByText("Nothing marked as posted yet.")).toBeInTheDocument();
    expect(cards()).toHaveLength(0);
    expect(tab("Not posted")).toHaveTextContent(/^Not posted3$/);
    expect(tab("Posted")).toHaveTextContent(/^Posted0$/);
  });

  it("a refused mark shows why on that card and leaves the list alone", async () => {
    vi.mocked(api.setPosted).mockRejectedValue(new ApiError(404, "No clip called '01-one.mp4'."));
    render(<RenderedPage />);
    await waitFor(() => expect(cards()).toHaveLength(2));
    await userEvent.click(within(card("One")).getByRole("button", { name: "Mark posted" }));
    expect(await within(card("One")).findByRole("status")).toHaveTextContent("No clip called '01-one.mp4'.");
    expect(within(card("Three")).queryByRole("status")).toBeNull();
    expect(titles()).toEqual(["One", "Three"]);
    expect(api.listClips).toHaveBeenCalledTimes(1);
  });

  it("with nothing rendered yet, says how to get there, on every filter", async () => {
    vi.mocked(api.listClips).mockResolvedValue([]);
    render(<RenderedPage />);
    const hint = "Nothing rendered yet. Open a job, pick a moment and press Render.";
    expect(await screen.findByText(hint)).toBeInTheDocument();
    expect(cards()).toHaveLength(0);
    for (const name of ["Not posted", "Posted", "All"] as const) {
      expect(tab(name)).toHaveTextContent(new RegExp(`^${name}0$`));
      await userEvent.click(tab(name));
      expect(screen.getByText(hint)).toBeInTheDocument();
    }
  });

  it("with everything posted, says so; with nothing posted, the Posted filter says that", async () => {
    vi.mocked(api.listClips).mockResolvedValue([renderedClip({ posted_at: before(HOUR) })]);
    const { unmount } = render(<RenderedPage />);
    expect(await screen.findByText("Everything you rendered is posted.")).toBeInTheDocument();
    expect(cards()).toHaveLength(0);
    await userEvent.click(tab("Posted"));
    expect(screen.queryByText("Everything you rendered is posted.")).toBeNull();
    expect(titles()).toEqual(["One"]);
    unmount();

    vi.mocked(api.listClips).mockResolvedValue([renderedClip()]);
    render(<RenderedPage />);
    await waitFor(() => expect(titles()).toEqual(["One"]));
    expect(screen.queryByText(/nothing|everything/i)).toBeNull();
    await userEvent.click(tab("Posted"));
    expect(screen.getByText("Nothing marked as posted yet.")).toBeInTheDocument();
    await userEvent.click(tab("All"));
    expect(screen.queryByText("Nothing marked as posted yet.")).toBeNull();
    expect(titles()).toEqual(["One"]);
  });

  it("shows no empty message while the first load is still pending", () => {
    vi.mocked(api.listClips).mockReturnValue(new Promise(() => {}));
    render(<RenderedPage />);
    expect(screen.getByRole("heading", { name: "Rendered clips" })).toBeInTheDocument();
    expect(screen.queryByText(/nothing|everything/i)).toBeNull();
    expect(tab("Not posted")).toHaveTextContent(/^Not posted0$/);
    expect(cards()).toHaveLength(0);
  });

  it("says why when the server refuses the list", async () => {
    vi.mocked(api.listClips).mockRejectedValue(new ApiError(500, "The clips folder can't be read."));
    render(<RenderedPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The clips folder can't be read.");
    expect(screen.queryByText(/nothing rendered yet/i)).toBeNull();
  });

  it("says so when the server can't be reached, then recovers", async () => {
    vi.mocked(api.listClips).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<RenderedPage />);
    expect(await screen.findByText(/can't reach clipper/i)).toBeInTheDocument();
    await waitFor(() => expect(titles()).toEqual(["One", "Three"]), { timeout: 4000 });
    expect(screen.queryByText(/can't reach clipper/i)).toBeNull();
  });
});
