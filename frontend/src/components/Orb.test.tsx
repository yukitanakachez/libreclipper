import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Orb, { OrbGrain } from "./Orb";

const blobs = (el: Element) => el.querySelector(".blobs") as HTMLElement;
const look = (el: Element) => { const b = blobs(el); return `${b.style.background}|${b.style.transform}`; };

describe("Orb", () => {
  it("the same id always renders the same orb", () => {
    const a = render(<Orb id="g-by68cnq6gc" />).container.firstElementChild as Element;
    const b = render(<Orb id="g-by68cnq6gc" />).container.firstElementChild as Element;
    expect(blobs(a).style.background).toMatch(/radial-gradient/);
    expect(look(a)).toBe(look(b));
  });

  it("different ids render different orbs", () => {
    const ids = ["g-by68cnq6gc", "g-vvbudk8xji", "i-8u4d4poic4", "i-2kq", "ZNRMRo1RNIg", "vid1"];
    const looks = ids.map((id) => look(render(<Orb id={id} />).container.firstElementChild as Element));
    expect(new Set(looks).size).toBe(ids.length);
  });

  it("is decorative, round, sized, with grain from the shared filter", () => {
    const orb = render(<Orb id="vid1" size={44} />).container.firstElementChild as HTMLElement;
    expect(orb).toHaveClass("orb");
    expect(orb).toHaveAttribute("aria-hidden", "true");
    expect(orb.style.width).toBe("44px");
    expect(orb.style.height).toBe("44px");
    expect(orb.querySelector(".grain [filter]")).toHaveAttribute("filter", "url(#orb-grain)");
    expect(orb.querySelector(".shine")).not.toBeNull();
  });

  it("defaults to 36 px", () => {
    const orb = render(<Orb id="vid1" />).container.firstElementChild as HTMLElement;
    expect(orb.style.width).toBe("36px");
  });

  it("OrbGrain renders the one shared grain filter", () => {
    render(<OrbGrain />);
    const filter = document.getElementById("orb-grain");
    expect(filter?.tagName.toLowerCase()).toBe("filter");
    expect(filter?.querySelector("feTurbulence")).not.toBeNull();
    expect(filter?.closest("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
