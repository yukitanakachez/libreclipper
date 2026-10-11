import { describe, expect, it } from "vitest";
import { href, parseHash, type Route } from "./route";

describe("routes", () => {
  it("survives a malformed link and opens old output links", () => {
    expect(parseHash("#/clips/%E0%A4")).toEqual({ id: null });
    expect(parseHash("#/jobs/vid1/output")).toEqual({ id: "vid1" });
  });

  it("parses the board and an open job", () => {
    expect(parseHash("")).toEqual({ id: null });
    expect(parseHash("#/")).toEqual({ id: null });
    expect(parseHash("#/clips")).toEqual({ id: null });
    expect(parseHash("#/clips/vid1")).toEqual({ id: "vid1" });
    expect(parseHash("#/clips/a%20b")).toEqual({ id: "a b" });
    expect(parseHash("#/clips/vid1/nonsense")).toEqual({ id: null });
    expect(parseHash("#/nonsense/x/y")).toEqual({ id: null });
  });

  it("parses the Rendered page, and only that exact link", () => {
    expect(parseHash("#/rendered")).toEqual({ id: null, rendered: true });
    expect(parseHash("#rendered")).toEqual({ id: null, rendered: true });
    expect(parseHash("#/rendered/x")).toEqual({ id: null });
    expect(parseHash("#/clips/rendered")).toEqual({ id: "rendered" });      // a job that happens to be called that
  });

  it("links to the sections that are gone open the board", () => {
    for (const hash of ["#/stories", "#/stories/r-abc123", "#/rankings/k-1", "#/photos", "#/posting"]) {
      expect(parseHash(hash)).toEqual({ id: null });
    }
  });

  it("keeps old review links working", () => {
    expect(parseHash("#/jobs/vid1")).toEqual({ id: "vid1" });
  });

  it("links to the board and to a job, encoding its id", () => {
    expect(href({ id: null })).toBe("#/");
    expect(href({ id: "vid1" })).toBe("#/clips/vid1");
    expect(href({ id: "a b" })).toBe("#/clips/a%20b");
    expect(href({ id: null, rendered: true })).toBe("#/rendered");
  });

  it("round-trips", () => {
    const routes: Route[] = [{ id: null }, { id: "vid1" }, { id: "a b/c" }, { id: null, rendered: true }];
    for (const r of routes) {
      expect(parseHash(href(r))).toEqual(r);
    }
  });
});
