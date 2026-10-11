import type {
  CandidateView, Clip, JobDetail, JobSummary, ProviderInfo, RenderedClip, Settings,
} from "./types";

export const job = (over: Partial<JobSummary> = {}): JobSummary => ({
  id: "vid1", title: "Episode 1", source: "https://youtu.be/vid1", campaign: "pod",
  state: "ready_for_review", progress: 0, failed_step: null, error: null,
  updated_at: "2026-09-24T10:00:00Z", candidates: 6, approved: 0, clips: 0, posted: 0, busy: false,
  ...over,
});

export const cand = (over: Partial<CandidateView> = {}): CandidateView => ({
  n: 1, start: 5, end: 9.9, orig_start: 5, orig_end: 9.9, headline: "One", hook: "w10",
  reason: "Because", score: 9, post_caption: "c1", hashtags: [], layout: "auto",
  music_on: false, music_track: null, approved: false, needs_check: false, edited: false,
  bounds: { min_start: 0, max_end: 14.9 },
  words: [{ i: 10, text: "w10", start: 5, end: 5.4 }, { i: 11, text: "w11.", start: 5.5, end: 5.9 }],
  finished_length: 4.45, in_limits: true, ends_on_sentence: true,
  clip: null, render_pending: false, render_error: null, reframe_pending: false, reframe_error: null,
  ...over,
});

export const detail = (over: Partial<JobDetail> = {}): JobDetail => ({
  id: "vid1", status: { state: "ready_for_review", error: null, failed_step: null },
  request: { campaign: "pod" }, meta: { title: "Episode", duration: 30 },
  campaign: { slug: "pod", name: "Pod", min_len: 2, max_len: 20, music_allowed: false, tracks: [] },
  candidates: [
    cand(),
    cand({ n: 2, start: 15, end: 19.9, headline: "Two", score: 8, needs_check: true,
           finished_length: 12.3 }),
  ],
  clips: [], busy: false, editable: true, ...over,
});

/** The clip rendered from moment 1 (`cand({ clip: "01-one.mp4" })`), not posted yet. */
export const clip = (over: Partial<Clip> = {}): Clip => ({
  file: "01-one.mp4", caption: "c1 #pod", headline: "One", version: "1-1",
  rendered_at: "2026-09-24T10:00:00Z", posted_at: null, ...over,
});

/** The same clip as the Rendered page lists it: with its job. */
export const renderedClip = (over: Partial<RenderedClip> = {}): RenderedClip => ({
  ...clip(), job_id: "vid1", job_title: "Episode 1", ...over,
});

export const provider = (over: Partial<ProviderInfo> = {}): ProviderInfo => ({
  id: "anthropic", name: "Anthropic", needs_key: true, key_url: "https://console.anthropic.com/settings/keys",
  has_key: false, key_hint: "", key_source: null, ready: false, model: "", ...over,
});

/** Anthropic, OpenAI and Ollama; `ready` says whether the one in use (Anthropic) has its key. */
export const settings = (over: Partial<Settings> = {}, ready = true): Settings => ({
  provider: ready ? "anthropic" : null, using: "anthropic", ready,
  providers: [
    provider(ready ? { has_key: true, key_hint: "abcd", key_source: "saved", ready: true } : {}),
    provider({ id: "openai", name: "OpenAI", key_url: "https://platform.openai.com/api-keys" }),
    provider({ id: "ollama", name: "Ollama (on this computer)", needs_key: false, key_url: "", ready: true }),
  ],
  ...over,
});
