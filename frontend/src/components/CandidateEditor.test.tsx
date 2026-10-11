import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { cand, detail } from "../test-fixtures";
import type { CandidateView, Word } from "../types";
import CandidateEditor from "./CandidateEditor";

vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { patchCandidate: vi.fn(), saveWordFixes: vi.fn() } };
});

const setup = (over: Partial<CandidateView> = {}) => {
  const onChanged = vi.fn();
  const c = cand(over);
  render(<CandidateEditor jobId="vid1" job={detail({ candidates: [c] })} candidate={c} onChanged={onChanged} />);
  return onChanged;
};

/** A clip from 5 to 9.9 s with words before, inside and after it. */
const longer: Word[] = [
  { i: 0, text: "a", start: 3, end: 3.4 }, { i: 1, text: "b", start: 3.5, end: 3.9 },
  { i: 2, text: "c", start: 5.1, end: 5.4 }, { i: 3, text: "d", start: 6, end: 6.4 },
  { i: 4, text: "e", start: 8, end: 8.4 }, { i: 5, text: "f", start: 9.5, end: 9.6 },
  { i: 6, text: "g", start: 11, end: 11.4 },
];
const word = (name: string) => screen.getByRole("option", { name });
const lastPatch = () => vi.mocked(api.patchCandidate).mock.calls.at(-1)?.[2];

beforeEach(() => {
  vi.mocked(api.patchCandidate).mockResolvedValue(cand());
  vi.mocked(api.saveWordFixes).mockResolvedValue({ fixes: {} });
});

describe("CandidateEditor", () => {
  it("click sets the start and shift-click sets the end", async () => {
    setup({ words: longer });
    await userEvent.click(word("e"));
    await waitFor(() => expect(api.patchCandidate).toHaveBeenCalledWith("vid1", 1, { start: 7.9 }));
    const user = userEvent.setup();
    await user.keyboard("{Shift>}");
    await user.click(word("g"));
    await user.keyboard("{/Shift}");
    await waitFor(() => expect(api.patchCandidate).toHaveBeenCalledWith("vid1", 1, { end: 11.7 }));
  });

  it("shift-click before the start leaves a valid range", async () => {
    setup({ words: longer });
    const user = userEvent.setup();
    await user.keyboard("{Shift>}");
    await user.click(word("a"));
    await user.keyboard("{/Shift}");
    await waitFor(() => expect(api.patchCandidate).toHaveBeenCalled());
    expect(lastPatch()).toEqual({ end: 6 });                     // at least a second after the start (5)
  });

  it("a click after the end leaves a valid range", async () => {
    setup({ words: longer });
    await userEvent.click(word("g"));
    await waitFor(() => expect(api.patchCandidate).toHaveBeenCalled());
    expect(lastPatch()).toEqual({ start: 8.9 });                 // at least a second before the end (9.9)
  });

  it("Enter and Shift+Enter in the transcript trim at the cursor", async () => {
    setup({ words: longer });
    screen.getByRole("listbox", { name: /transcript/i }).focus();
    await userEvent.keyboard("{ArrowRight}{ArrowRight}{Enter}");        // cursor c → e
    await waitFor(() => expect(lastPatch()).toEqual({ start: 7.9 }));
    await userEvent.keyboard("{ArrowRight}{ArrowRight}{Shift>}{Enter}{/Shift}");
    await waitFor(() => expect(lastPatch()).toEqual({ end: 11.7 }));
  });

  it("⌘Z undoes the last trim, then the one before, and nothing more", async () => {
    const onChanged = vi.fn();
    const job = detail();
    const view = (c: CandidateView) =>
      <CandidateEditor jobId="vid1" job={job} candidate={c} onChanged={onChanged} />;
    const { rerender } = render(view(cand({ words: longer })));
    await userEvent.click(word("e"));                                     // start 5 → 7.9
    await waitFor(() => expect(lastPatch()).toEqual({ start: 7.9 }));
    rerender(view(cand({ words: longer, start: 7.9 })));
    await userEvent.click(screen.getByRole("button", { name: "End +0.5" }));  // end 9.9 → 10.4
    await waitFor(() => expect(lastPatch()).toEqual({ end: 10.4 }));
    rerender(view(cand({ words: longer, start: 7.9, end: 10.4 })));

    fireEvent.keyDown(document, { key: "z", metaKey: true });
    await waitFor(() => expect(lastPatch()).toEqual({ start: 7.9, end: 9.9 }));
    rerender(view(cand({ words: longer, start: 7.9, end: 9.9 })));
    fireEvent.keyDown(document, { key: "z", metaKey: true });
    await waitFor(() => expect(lastPatch()).toEqual({ start: 5, end: 9.9 }));
    const calls = vi.mocked(api.patchCandidate).mock.calls.length;
    fireEvent.keyDown(document, { key: "z", metaKey: true });
    await act(async () => { await Promise.resolve(); });
    expect(api.patchCandidate).toHaveBeenCalledTimes(calls);
  });

  it("⌘Z does nothing while typing in a field", async () => {
    setup({ words: longer });
    await userEvent.click(word("e"));
    await waitFor(() => expect(lastPatch()).toEqual({ start: 7.9 }));
    const headline = screen.getByLabelText("Headline");
    fireEvent.keyDown(headline, { key: "z", metaKey: true });
    await act(async () => { await Promise.resolve(); });
    expect(api.patchCandidate).toHaveBeenCalledTimes(1);
  });

  it("a trim shows a small Undo button that puts it back", async () => {
    setup({ words: longer });
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    await userEvent.click(word("e"));
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(lastPatch()).toEqual({ start: 5, end: 9.9 }));
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("the Undo button goes after 10 s", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      setup({ words: longer });
      await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(word("e"));
      expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
      act(() => { vi.advanceTimersByTime(10_000); });
      expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("Tab and Shift+Tab don't hide the Undo button", async () => {
    setup({ words: longer });
    await userEvent.click(word("e"));
    expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
    await userEvent.tab();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
  });

  it("a new trim with ↵ in the transcript shows Undo again and restarts its 10 s", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      setup({ words: longer });
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      await user.click(word("e"));
      expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
      act(() => { vi.advanceTimersByTime(6_000); });
      screen.getByRole("listbox", { name: /transcript/i }).focus();
      await user.keyboard("{Enter}");
      expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
      act(() => { vi.advanceTimersByTime(6_000); });                // 12 s after the first trim
      expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
      act(() => { vi.advanceTimersByTime(4_000); });
      expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("two quick trims before a reload undo step by step", async () => {
    setup({ words: longer });                                       // 5 → 9.9, never re-rendered
    await userEvent.click(word("e"));                               // start 7.9
    await userEvent.click(screen.getByRole("button", { name: "End +0.5" }));
    await waitFor(() => expect(lastPatch()).toEqual({ end: 10.4 }));
    fireEvent.keyDown(document.body, { key: "z", metaKey: true });
    await waitFor(() => expect(lastPatch()).toEqual({ start: 7.9, end: 9.9 }));
    fireEvent.keyDown(document.body, { key: "z", metaKey: true });
    await waitFor(() => expect(lastPatch()).toEqual({ start: 5, end: 9.9 }));
  });

  it("the Undo button goes at the next action", async () => {
    setup({ words: longer });
    await userEvent.click(word("e"));
    expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
    await userEvent.click(screen.getByText(/headline, caption, layout/i));
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("a double-click's undone pick leaves nothing for ⌘Z", async () => {
    setup({ words: longer });
    await userEvent.dblClick(word("e"));
    await screen.findByRole("textbox", { name: /fix spelling/i });
    await waitFor(() => expect(lastPatch()).toEqual({ start: 5, end: 9.9 }));
    const calls = vi.mocked(api.patchCandidate).mock.calls.length;
    fireEvent.keyDown(document.body, { key: "z", metaKey: true });
    await act(async () => { await Promise.resolve(); });
    expect(api.patchCandidate).toHaveBeenCalledTimes(calls);
  });

  it("shows the trim line and has no start/end mode switch", () => {
    setup({ start: 760.2, end: 778.4, bounds: { min_start: 700, max_end: 800 } });
    expect(screen.getByText("12:40.2")).toBeInTheDocument();
    expect(screen.getByText("12:58.4")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /approve/i })).toBeNull();
  });

  it("nudges the start by half a second", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: /start −0\.5/i }));
    expect(api.patchCandidate).toHaveBeenCalledWith("vid1", 1, { start: 4.5 });
  });

  it("double-clicking a word fixes its spelling and leaves the trim where it was", async () => {
    setup();
    await userEvent.dblClick(word("w11."));
    const input = screen.getByRole("textbox", { name: /fix spelling/i });
    await userEvent.clear(input);
    await userEvent.type(input, "eleven.{Enter}");
    expect(api.saveWordFixes).toHaveBeenCalledWith("vid1", { "11": "eleven." });
    await waitFor(() => expect(vi.mocked(api.patchCandidate).mock.calls.at(-1))
      .toEqual(["vid1", 1, { start: 5, end: 9.9 }]));
  });

  it("a slow double-click still leaves the trim where it was", async () => {
    setup();
    const w = word("w11.");
    fireEvent.click(w, { detail: 1 });
    await new Promise((r) => setTimeout(r, 600));            // slower than any fixed wait
    fireEvent.click(w, { detail: 2 });
    fireEvent.dblClick(w, { detail: 2 });
    expect(await screen.findByRole("textbox", { name: /fix spelling/i })).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(api.patchCandidate).mock.calls.at(-1))
      .toEqual(["vid1", 1, { start: 5, end: 9.9 }]));
  });

  it("a single click trims straight away", async () => {
    setup();
    await userEvent.click(word("w11."));
    expect(api.patchCandidate).toHaveBeenCalledWith("vid1", 1, { start: 5.45 });
  });

  it("opens the spelling fix with the word selected, so typing replaces it", async () => {
    setup();
    await userEvent.dblClick(word("w11."));
    await userEvent.keyboard("eleven.{Enter}");
    expect(api.saveWordFixes).toHaveBeenCalledWith("vid1", { "11": "eleven." });
  });

  it("locks trims while the framing is being redone", async () => {
    setup({ reframe_pending: true });
    expect(screen.getByRole("button", { name: /start −0\.5/i })).toBeDisabled();
    expect(screen.getByRole("listbox", { name: /transcript/i })).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(screen.getByText(/headline, caption, layout & music/i));
    expect(screen.getByRole("combobox", { name: /layout/i })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: /headline/i })).toBeEnabled();
  });

  it("folds headline, caption, layout and music into one row", async () => {
    setup();
    const fold = screen.getByText(/headline, caption, layout & music/i).closest("details");
    expect(fold).not.toHaveAttribute("open");
    await userEvent.click(screen.getByText(/headline, caption, layout & music/i));
    expect(fold).toHaveAttribute("open");
  });

  it("saves the headline on blur", async () => {
    setup();
    await userEvent.click(screen.getByText(/headline, caption, layout & music/i));
    const field = screen.getByRole("textbox", { name: /headline/i });
    await userEvent.clear(field);
    await userEvent.type(field, "Better headline");
    await userEvent.tab();
    expect(api.patchCandidate).toHaveBeenCalledWith("vid1", 1, { headline: "Better headline" });
  });

  it("shows the limit warning", () => {
    setup({ finished_length: 25.2, in_limits: false });
    expect(screen.getByText(/outside this campaign's 2–20 s/)).toBeInTheDocument();
  });

  it("hints when the end is not a finished sentence", () => {
    setup({ ends_on_sentence: false });
    expect(screen.getByText(/doesn't end on a finished sentence/i)).toBeInTheDocument();
  });

  it("shows a server rejection inline", async () => {
    vi.mocked(api.patchCandidate).mockRejectedValue(new Error("Trim must stay within 0.0-14.9 s (the analyzed range)."));
    setup();
    await userEvent.click(screen.getByRole("button", { name: /end \+0\.5/i }));
    expect(await screen.findByText(/analyzed range/)).toBeInTheDocument();
  });

  it("disables editing while the job is busy", () => {
    const c = cand();
    render(<CandidateEditor jobId="vid1" job={detail({ editable: false, candidates: [c] })} candidate={c} onChanged={vi.fn()} />);
    expect(screen.getByRole("button", { name: /end \+0\.5/i })).toBeDisabled();
    expect(screen.getByRole("listbox", { name: /transcript/i })).toHaveAttribute("aria-disabled", "true");
  });
});
