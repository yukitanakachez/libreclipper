import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Icon, { type IconName } from "./Icon";

describe("Icon", () => {
  it.each<IconName>(["play", "copy", "trash", "gear", "retry", "back", "x", "bell", "film", "folder", "plus", "alert"])(
    "%s renders a decorative 16 px line svg", (name) => {
      const { container } = render(<Icon name={name} />);
      const svg = container.querySelector("svg") as SVGSVGElement;
      expect(svg).not.toBeNull();
      expect(svg).toHaveAttribute("aria-hidden", "true");
      expect(svg).toHaveAttribute("focusable", "false");
      expect(svg).toHaveAttribute("viewBox", "0 0 24 24");
      expect(svg).toHaveAttribute("width", "16");
      expect(svg).toHaveAttribute("stroke", "currentColor");
      expect(svg).toHaveAttribute("fill", "none");
      expect(svg.children.length).toBeGreaterThan(0);
    });

  it("different names draw different shapes", () => {
    const a = render(<Icon name="play" />).container.innerHTML;
    const b = render(<Icon name="trash" />).container.innerHTML;
    expect(a).not.toBe(b);
  });
});
