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
    expect(await api.createJob("/videos/abc.mp4", "pod", "@jane")).toEqual({ id: "abc", existing: false });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/jobs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ source: "/videos/abc.mp4", campaign: "pod", creator: "@jane" });
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

  it("sends a dropped video as the request body, reports progress, and returns where it was kept", async () => {
    const sent: unknown[] = [];
    class FakeXhr {
      upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
      status = 0; responseText = ""; statusText = ""; url = "";
      onload?: () => void; onerror?: () => void;
      open(_method: string, url: string) { this.url = url; }
      send(body: unknown) {
        sent.push(this.url, body);
        this.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 4 });
        this.status = 200; this.responseText = JSON.stringify({ path: "/jobs/uploads/Ep 1.mp4" });
        this.onload?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const file = new File(["data"], "Ep 1.mp4");
    const progress = vi.fn();
    expect(await api.uploadVideo(file, progress)).toEqual({ path: "/jobs/uploads/Ep 1.mp4" });
    expect(sent).toEqual(["/api/uploads?name=Ep%201.mp4", file]);
    expect(progress).toHaveBeenCalledWith(0.25);
  });

  it("a refused upload rejects with the server's reason", async () => {
    class FakeXhr {
      upload = {}; status = 400; responseText = JSON.stringify({ detail: "That file is empty." }); statusText = "Bad Request";
      onload?: () => void;
      open() {}
      send() { this.onload?.(); }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    await expect(api.uploadVideo(new File([], "e.mp4"))).rejects.toThrow("That file is empty.");
  });
});
