import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Word } from "../types";
import TranscriptWords from "./TranscriptWords";

const words: Word[] = [
  { i: 0, text: "and", start: 3, end: 3.4 },
  { i: 1, text: "nobody", start: 5, end: 5.4 },
  { i: 2, text: "trusts", start: 5.5, end: 5.9 },
  { i: 3, text: "experts.", start: 6, end: 6.4 },
  { i: 4, text: "Anyway", start: 8, end: 8.4 },
];

function setup(over: Partial<Parameters<typeof TranscriptWords>[0]> = {}) {
  const props = {
    words, start: 4.9, end: 6.7, disabled: false,
    onPickStart: vi.fn(), onPickEnd: vi.fn(), onUndoPick: vi.fn(), onFix: vi.fn(), ...over,
  };
  render(<TranscriptWords {...props} />);
  return props;
}
const box = () => screen.getByRole("listbox", { name: /transcript/i });
const cursorWord = () => document.getElementById(box().getAttribute("aria-activedescendant") ?? "");

describe("TranscriptWords", () => {
  it("is flowing text in one tab stop, with the clip's words selected", () => {
    setup();
    expect(box()).toHaveAttribute("tabindex", "0");
    expect(box()).toHaveAttribute("title", "Click: start here · ⇧-click: end here · double-click: fix spelling");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    const selected = screen.getAllByRole("option").filter((o) => o.getAttribute("aria-selected") === "true");
    expect(selected.map((o) => o.textContent?.trim())).toEqual(["nobody", "trusts", "experts."]);
    expect(screen.getByRole("option", { name: "and" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("option", { name: "nobody" })).toHaveClass("start");
    expect(screen.getByRole("option", { name: "experts." })).toHaveClass("end");
  });

  it("has only options as the listbox's visible children", () => {
    setup();
    const stray = [...box().children].filter((el) => el.getAttribute("role") !== "option"
      && el.getAttribute("aria-hidden") !== "true");
    expect(stray).toEqual([]);
    expect([...box().childNodes].filter((n) => n.nodeType === Node.TEXT_NODE)).toEqual([]);
  });

  it("click picks the start and shift-click the end", async () => {
    const props = setup();
    await userEvent.click(screen.getByRole("option", { name: "trusts" }));
    expect(props.onPickStart).toHaveBeenCalledWith(2);
    const user = userEvent.setup();
    await user.keyboard("{Shift>}");
    await user.click(screen.getByRole("option", { name: "Anyway" }));
    await user.keyboard("{/Shift}");
    expect(props.onPickEnd).toHaveBeenCalledWith(4);
    expect(props.onPickStart).toHaveBeenCalledTimes(1);
  });

  it("Enter and Shift+Enter on the keyboard cursor trim", async () => {
    const props = setup();
    box().focus();
    expect(cursorWord()?.textContent?.trim()).toBe("nobody");          // starts on the clip's first word
    await userEvent.keyboard("{ArrowRight}{Enter}");
    expect(props.onPickStart).toHaveBeenCalledWith(2);
    await userEvent.keyboard("{ArrowRight}{ArrowRight}{Shift>}{Enter}{/Shift}");
    expect(props.onPickEnd).toHaveBeenCalledWith(4);
    expect(cursorWord()).toHaveClass("cursor");
  });

  it("arrow keys stop at the first and last word", async () => {
    setup();
    box().focus();
    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}{ArrowLeft}");
    expect(cursorWord()?.textContent?.trim()).toBe("and");
    await userEvent.keyboard("{ArrowRight}".repeat(9));
    expect(cursorWord()?.textContent?.trim()).toBe("Anyway");
  });

  it("F2 fixes the spelling of the word under the cursor", async () => {
    const props = setup();
    box().focus();
    await userEvent.keyboard("{ArrowRight}{F2}");
    const input = screen.getByRole("textbox", { name: /fix spelling/i });
    expect(input).toHaveValue("trusts");
    await userEvent.keyboard("trust's{Enter}");
    expect(props.onFix).toHaveBeenCalledWith(words[2], "trust's");
    expect(props.onPickStart).not.toHaveBeenCalled();               // Enter in the box isn't a trim
    expect(box()).toHaveFocus();
  });

  it("a double-click undoes its first click's trim and opens the spelling fix", async () => {
    const props = setup();
    await userEvent.dblClick(screen.getByRole("option", { name: "experts." }));
    expect(props.onPickStart).toHaveBeenCalledTimes(1);
    expect(props.onUndoPick).toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: /fix spelling/i })).toHaveValue("experts.");
  });

  it("does nothing while trims are locked", async () => {
    const props = setup({ disabled: true });
    expect(box()).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(screen.getByRole("option", { name: "trusts" }), { detail: 1 });
    box().focus();
    await userEvent.keyboard("{Enter}{F2}");
    expect(props.onPickStart).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});
