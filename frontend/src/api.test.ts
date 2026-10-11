import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, media } from "./api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status < 400, status, statusText: "x",
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("creates a job with a JSON POST", async () => {
    const fetch = mockFetch(201, { id: "abc", existing: false });
    expect(await api.createJob("https://youtu.be/abc", "pod")).toEqual({ id: "abc", existing: false });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/jobs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ source: "https://youtu.be/abc", campaign: "pod" });
  });

  it("surfaces the server's error detail", async () => {
    mockFetch(422, { detail: "Trim must stay within 0.0-14.9 s (the analyzed range)." });
    await expect(api.patchCandidate("vid1", 1, { end: 99 })).rejects.toThrow("analyzed range");
    await expect(api.patchCandidate("vid1", 1, { end: 99 })).rejects.toBeInstanceOf(ApiError);
  });

  it("encodes job ids in URLs", async () => {
    const fetch = mockFetch(200, {});
    await api.getJob("a b");
    expect(fetch.mock.calls[0][0]).toBe("/api/jobs/a%20b");
  });

  it("asks for one moment's render with a bodiless POST to that candidate", async () => {
    const fetch = mockFetch(200, { queued: true });
    expect(await api.render("a b", 3)).toEqual({ queued: true });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/jobs/a%20b/candidates/3/render");
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
  });

  it("lists every rendered clip", async () => {
    const fetch = mockFetch(200, []);
    expect(await api.listClips()).toEqual([]);
    expect(fetch.mock.calls[0][0]).toBe("/api/clips");
  });

  it("marks a clip posted, or not, with a PUT to the clip", async () => {
    const fetch = mockFetch(200, {});
    await api.setPosted("a b", "01 x.mp4", true);
    await api.setPosted("a b", "01 x.mp4", false);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/jobs/a%20b/clips/01%20x.mp4/posted");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ posted: true });
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ posted: false });
  });

  it("builds media URLs", () => {
    expect(media.proxy("vid1")).toBe("/media/vid1/proxy.mp4");
    expect(media.clip("vid1", "01 x.mp4", "123-45")).toBe("/media/vid1/clips/01%20x.mp4?v=123-45");
    expect(media).not.toHaveProperty("preview");
  });
});
