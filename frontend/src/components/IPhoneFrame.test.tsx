import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import IPhoneFrame from "./IPhoneFrame";

afterEach(() => vi.restoreAllMocks());

describe("IPhoneFrame", () => {
  it("is a devices.css iPhone 14 Pro with the content on its screen", () => {
    const { container } = render(<IPhoneFrame><p>hello</p></IPhoneFrame>);
    expect(container.querySelector(".device.device-iphone-14-pro")).not.toBeNull();
    expect(container.querySelector(".device-screen")).toContainElement(screen.getByText("hello"));
    for (const part of ["device-header", "device-sensors", "device-btns", "device-power"]) {
      expect(container.querySelector(`.${part}`)).not.toBeNull();
    }
  });

  it("scales to the height of its box", () => {
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(434);
    const { container } = render(<IPhoneFrame />);
    expect((container.querySelector(".device") as HTMLElement).style.transform).toBe("scale(0.5)");
  });

  it("shrinks to fit a narrow box instead of overflowing it", () => {
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(868);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(107);
    const { container } = render(<IPhoneFrame />);
    expect((container.querySelector(".device") as HTMLElement).style.transform).toBe("scale(0.25)");
  });

  it("hands out the screen element for portals", () => {
    const seen: (HTMLDivElement | null)[] = [];
    render(<IPhoneFrame screenRef={(el) => seen.push(el)} />);
    expect(seen[0]?.className).toBe("device-screen");
  });
});
