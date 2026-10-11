import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { announce } from "../announce";
import Problem, { explain } from "./Problem";

vi.mock("../announce");

describe("explain", () => {
  it("maps missing Anthropic auth by message or status code, and points at Settings", () => {
    for (const message of ["Could not resolve authentication method",
                           "anthropic.APIStatusError: Error code: 401 - unauthorized",
                           "Error code: 401 - {'type': 'error', 'error': {'message': 'invalid x-api-key'}}",
                           "Claude returned 401"]) {
      expect(explain(message)).toEqual({ text: "Claude isn't signed in.", fix: "Add your Anthropic API key in Settings.",
                                         settings: true, details: message });
    }
    // A 401 from somewhere else is not Claude's.
    expect(explain("Reddit returned 401 for that post.")).toEqual({ text: "Reddit returned 401 for that post." });
  });

  it("maps a missing key, a missing model and a refused key for any provider", () => {
    expect(explain("No OpenAI API key yet. Add one in Settings.")).toEqual({
      text: "No OpenAI API key yet.", fix: "Add the key in Settings, then press Retry.", settings: true });
    expect(explain("No Google Gemini model chosen yet. Pick one in Settings.")).toEqual({
      text: "No Google Gemini model chosen yet.", fix: "Choose a model in Settings, then press Retry.", settings: true });
    // Anthropic's refusal carries "invalid x-api-key", which must not read as "not signed in".
    const anthropic = "Anthropic didn't accept that API key. (invalid x-api-key)";
    expect(explain(anthropic)).toMatchObject({ text: "Anthropic didn't accept that API key.", details: anthropic });
    const refused = "OpenAI didn't accept that API key. (Incorrect API key provided)";
    expect(explain(refused)).toEqual({
      text: "OpenAI didn't accept that API key.",
      fix: "Paste the key again in Settings, or make a new one with your provider.", settings: true, details: refused });
  });

  it("maps rate limits and empty credit to waiting or billing", () => {
    for (const message of ["OpenAI answered 429: slow down", "Your credit balance is too low", "insufficient_quota"]) {
      const e = explain(message);
      expect(e.text).toMatch(/turned the request away/);
      expect(e.fix).toMatch(/Wait a minute and press Retry/);
      expect(e.details).toBe(message);
      expect(e.settings).toBeUndefined();
    }
  });

  it("maps an ffmpeg that can't draw captions, is missing, or is for another kind of computer", () => {
    for (const message of ["No option name near '.ass' for filter", "No such filter: 'ass'"]) {
      expect(explain(message)).toMatchObject({ text: "This ffmpeg can't draw captions.", settings: true });
    }
    for (const message of ["[Errno 86] Bad CPU type in executable: 'ffmpeg'",
                           "[Errno 2] No such file or directory: 'ffmpeg'"]) {
      expect(explain(message)).toMatchObject({ text: "ffmpeg is missing or can't run on this computer.", settings: true,
                                               details: message });
    }
    expect(explain("MediaPipe model missing: /x/face_landmarker.task. Run clipper setup to download it."))
      .toMatchObject({ text: "A file Clipper needs isn't installed yet.", settings: true });
  });

  it("maps YouTube refusing or hiding a video to what to do instead", () => {
    expect(explain("YouTube refused this clip's download 3 times (403). Wait a minute and press Retry")).toMatchObject({
      text: "YouTube refused the download.", fix: expect.stringMatching(/Choose file… in New/) });
    expect(explain("YouTube changed something and yt-dlp needs updating. Run: uv run yt-dlp -U")).toMatchObject({
      text: "YouTube changed something and the downloader is out of date.", fix: expect.stringMatching(/\.\/start/) });
    expect(explain("This video is private.")).toEqual({
      text: "This video is private.", fix: "If you have the video, download it yourself and use Choose file… in New." });
  });

  it("maps a full disk and a broken campaign file", () => {
    expect(explain("ffmpeg failed: No space left on device")).toMatchObject({ text: "This computer's disk is full." });
    expect(explain("pod.yaml: 'name' is required")).toEqual({
      text: "pod.yaml: 'name' is required", fix: "Fix that file in the campaigns folder, then try again." });
  });

  it("maps offline fetch failures and bare server errors", () => {
    expect(explain("Failed to fetch")).toEqual({
      text: "Can't reach Clipper. Retrying…",
      fix: "If this doesn't clear up, start Clipper again (./start) and reload this page." });
    expect(explain("Internal Server Error")).toMatchObject({ text: "Clipper hit an unexpected error." });
    expect(explain("Clipper hit an unexpected error: KeyError: 'campaign'")).toMatchObject({
      text: "Clipper hit an unexpected error.", details: "Clipper hit an unexpected error: KeyError: 'campaign'" });
  });

  it("keeps an unrecognised single-line message as is, with no details", () => {
    expect(explain("Disk full.")).toEqual({ text: "Disk full." });
  });

  it("unknown messages keep their first line and details", () => {
    const message = "Something broke\nTraceback (most recent call last):\n  File x, line 1";
    expect(explain(message)).toEqual({ text: "Something broke", details: message });
  });
});

describe("Problem", () => {
  it("announces the mapped sentence and fix once, on mount", () => {
    render(<Problem message="Could not resolve authentication method" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Claude isn't signed in.");
    expect(alert).toHaveTextContent("How to fix: Add your Anthropic API key in Settings.");
    expect(screen.getByRole("link", { name: "Open Settings" })).toHaveAttribute("href", "#/settings");
  });

  it("shows an unmapped message plainly, with no Details, fix or Settings link for one line", () => {
    render(<Problem message="Disk full." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Disk full.");
    expect(screen.queryByText("Details")).toBeNull();
    expect(screen.queryByText(/how to fix/i)).toBeNull();
    expect(screen.queryByRole("link", { name: "Open Settings" })).toBeNull();
  });

  it("puts a multi-line unknown message behind Details", () => {
    render(<Problem message={"boom\nline two"} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.queryByText("line two")).toBeNull();
    expect(screen.getByText("Details")).toBeInTheDocument();
    expect(document.querySelector(".problem pre")?.textContent).toBe("boom\nline two");
  });

  it("on the Settings page itself, a Settings fix has no link to Settings", () => {
    render(<Problem message="No OpenAI API key yet. Add one in Settings." inSettings />);
    expect(screen.getByRole("alert")).toHaveTextContent("How to fix: Add the key in Settings, then press Retry.");
    expect(screen.queryByRole("link", { name: "Open Settings" })).toBeNull();
  });

  it("has no dismiss button unless onDismiss is passed", () => {
    render(<Problem message="Disk full." />);
    expect(screen.queryByRole("button", { name: /dismiss/i })).toBeNull();
  });

  it("dismisses on click", async () => {
    const onDismiss = vi.fn();
    render(<Problem message="Disk full." onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it("is announced once, by its role=alert, not also through the status announcer", () => {
    render(<Problem message="Could not resolve authentication method" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Claude isn't signed in.");
    expect(announce).not.toHaveBeenCalled();
  });

  it("a persistent problem is a status, so it isn't re-announced as an alert on every render", () => {
    render(<Problem message="Disk full." persistent />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Disk full.");
  });
});

describe("Problem dismiss button", () => {
  it("is an icon-only ghost x that keeps the name Dismiss", () => {
    render(<Problem message="Disk full." onDismiss={vi.fn()} />);
    const dismiss = screen.getByRole("button", { name: "Dismiss" });
    expect(dismiss).toHaveClass("ghost", "icon-only");
    expect(dismiss.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(dismiss).not.toHaveTextContent("×");
  });
});
