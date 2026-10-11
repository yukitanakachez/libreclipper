import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { cand, clip, detail } from "../test-fixtures";
import MomentList from "./MomentList";

describe("MomentList", () => {
  it("J moves the selection to the next moment, K to the previous, in picked order", async () => {
    const onSelect = vi.fn();
    const job = detail({ candidates: [cand({ n: 1, headline: "One" }), cand({ n: 2, headline: "Two" })] });
    render(<MomentList job={job} selected={1} onSelect={onSelect} />);
    await screen.findByRole("button", { name: /One/ });
    await userEvent.keyboard("j");
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("with nothing selected, J picks the first moment", async () => {
    const onSelect = vi.fn();
    const job = detail({ candidates: [cand({ n: 1, headline: "One" }), cand({ n: 2, headline: "Two" })] });
    render(<MomentList job={job} selected={null} onSelect={onSelect} />);
    await screen.findByRole("button", { name: /One/ });
    await userEvent.keyboard("j");
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("K does nothing at the first moment", async () => {
    const onSelect = vi.fn();
    const job = detail({ candidates: [cand({ n: 1, headline: "One" }), cand({ n: 2, headline: "Two" })] });
    render(<MomentList job={job} selected={1} onSelect={onSelect} />);
    await screen.findByRole("button", { name: /One/ });
    await userEvent.keyboard("k");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("J does nothing at the last moment", async () => {
    const onSelect = vi.fn();
    const job = detail({ candidates: [cand({ n: 1, headline: "One" }), cand({ n: 2, headline: "Two" })] });
    render(<MomentList job={job} selected={2} onSelect={onSelect} />);
    await screen.findByRole("button", { name: /Two/ });
    await userEvent.keyboard("j");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("a posted moment is marked: a check, the word Posted, and a tinted row", () => {
    const job = detail({
      candidates: [cand({ n: 1, headline: "One", clip: "01-one.mp4" }), cand({ n: 2, headline: "Two", clip: "02-two.mp4" }),
                   cand({ n: 3, headline: "Three", clip: "03-three.mp4", render_pending: true })],
      clips: [clip({ posted_at: "2026-09-25T10:00:00Z" }), clip({ file: "02-two.mp4" }),
              clip({ file: "03-three.mp4", posted_at: "2026-09-25T10:00:00Z" })],
    });
    render(<MomentList job={job} selected={2} onSelect={vi.fn()} />);
    const one = screen.getByRole("button", { name: /One/ });
    expect(one).toHaveClass("posted");
    expect(within(one).getByText("Posted")).toHaveClass("ok");
    expect(one.querySelector("svg.icon")).not.toBeNull();
    expect(one).not.toHaveTextContent("Rendered");
    const two = screen.getByRole("button", { name: /Two/ });
    expect(two).not.toHaveClass("posted");
    expect(two).toHaveTextContent("Rendered");
    // Being rendered again: the old clip's mark doesn't speak for the new one.
    expect(screen.getByRole("button", { name: /Three/ })).not.toHaveClass("posted");
  });

  it("a moment with a clip says Rendered, one being rendered says Rendering…, the rest neither", () => {
    const job = detail({ candidates: [
      cand({ n: 1, headline: "One", clip: "01-one.mp4" }),
      cand({ n: 2, headline: "Two", render_pending: true }),
      cand({ n: 3, headline: "Three", clip: "03-three.mp4", render_pending: true }),   // being rendered again
      cand({ n: 4, headline: "Four", approved: true }),
    ] });
    render(<MomentList job={job} selected={1} onSelect={vi.fn()} />);
    const one = screen.getByRole("button", { name: /One/ });
    expect(within(one).getByText("Rendered")).toHaveClass("ok");
    expect(one).not.toHaveTextContent("Rendering…");
    expect(screen.getByRole("button", { name: /Two/ })).toHaveTextContent("4.5 s · Rendering…");
    expect(screen.getByRole("button", { name: /Three/ })).toHaveTextContent("Rendering…");
    expect(within(screen.getByRole("button", { name: /Three/ })).queryByText("Rendered")).toBeNull();
    expect(screen.getByRole("button", { name: /Four/ })).not.toHaveTextContent(/render|approved/i);
  });

  it("does nothing while no job is loaded", async () => {
    const onSelect = vi.fn();
    render(<MomentList job={null} selected={null} onSelect={onSelect} />);
    await userEvent.keyboard("j");
    expect(onSelect).not.toHaveBeenCalled();
  });
});
