type JobState =
  | "queued" | "fetching" | "transcribing" | "picking" | "reframing"
  | "ready_for_review" | "rendering" | "done" | "failed";

/** Waiting on you, or finished. In every other state Clipper is working on the job. */
const SETTLED: string[] = ["ready_for_review", "failed", "done"];
export const isWorking = (state: string): boolean => !SETTLED.includes(state);

export interface JobSummary {
  id: string; title: string | null; source: string | null; campaign: string | null;
  state: JobState; progress: number; failed_step: string | null; error: string | null;
  updated_at: string | null; candidates: number; approved: number; clips: number; posted: number; busy: boolean;
}

export interface Word { i: number; text: string; start: number; end: number }

export type Layout = "auto" | "stack" | "fit";

export interface CandidateView {
  n: number; start: number; end: number; orig_start: number; orig_end: number;
  headline: string; hook: string; reason: string; score: number; post_caption: string;
  hashtags: string[]; layout: Layout; music_on: boolean; music_track: string | null;
  approved: boolean; needs_check: boolean; edited: boolean;
  bounds: { min_start: number; max_end: number };
  words: Word[]; finished_length: number | null; in_limits: boolean | null;
  ends_on_sentence: boolean;
  clip: string | null;              // its rendered clip's file name, once it has one
  render_pending: boolean; render_error: string | null;
  reframe_pending: boolean; reframe_error: string | null;
}

interface CampaignInfo {
  slug: string; name: string; min_len: number; max_len: number;
  music_allowed: boolean; tracks: string[];
}

/** A rendered clip. `posted_at` is when you marked it posted (null: not posted yet). */
export interface Clip {
  file: string; caption: string; headline: string | null; version: string;
  rendered_at: string; posted_at: string | null;
}

/** A clip on the Rendered page: with the job it came from. */
export interface RenderedClip extends Clip { job_id: string; job_title: string | null }

export interface JobDetail {
  id: string;
  status: { state: JobState; error: string | null; failed_step: string | null; updated_at?: string;
            progress?: number };
  request: { source?: string; campaign?: string };
  meta: { title: string; duration: number } | null;
  campaign: CampaignInfo | null;
  candidates: CandidateView[];
  clips: Clip[];
  busy: boolean;
  editable: boolean;
}

export interface CampaignListing { slug: string; name: string | null; valid: boolean; error: string | null }

export type CandidatePatch = Partial<Pick<CandidateView,
  "start" | "end" | "headline" | "post_caption" | "layout" | "music_on" | "music_track">>;

/** One AI provider on the Settings page. The key itself never reaches the browser: only whether
 *  there is one, its last four characters, and where it came from. */
export interface ProviderInfo {
  id: string; name: string; needs_key: boolean; key_url: string;
  has_key: boolean; key_hint: string;
  key_source: string | null;        // "saved", or the shell variable it was found in
  ready: boolean; model: string;
}

/** `provider` is the one you chose (null: never chose); `using` is the one in use. */
export interface Settings { provider: string | null; using: string; ready: boolean; providers: ProviderInfo[] }

export interface SetupCheck { name: string; ok: boolean; fix: string }
