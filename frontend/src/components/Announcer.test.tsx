import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { announce } from "../announce";
import Announcer from "./Announcer";

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

describe("Announcer", () => {
  it("writes announced text into the live region", () => {
    render(<Announcer />);
    act(() => { announce("Part 1 voiced"); vi.runAllTimers(); });
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("Part 1 voiced");
    expect(region).toHaveAttribute("aria-live", "polite");
  });

  it("clears then re-sets to force a second announcement of the same text", () => {
    render(<Announcer />);
    act(() => { announce("Copied title"); vi.runAllTimers(); });
    expect(screen.getByRole("status")).toHaveTextContent("Copied title");
    act(() => { announce("Copied title"); });
    expect(screen.getByRole("status")).toHaveTextContent("");
    act(() => { vi.runAllTimers(); });
    expect(screen.getByRole("status")).toHaveTextContent("Copied title");
  });
});
