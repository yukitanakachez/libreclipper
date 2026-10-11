import type {
  CampaignListing, CandidatePatch, CandidateView, Clip, JobDetail, JobSummary, RenderedClip, Settings,
  SetupCheck,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** FastAPI's list of what was wrong with a request, as a sentence: "source: Field required". */
function describeDetail(detail: unknown): string {
  if (!Array.isArray(detail)) return JSON.stringify(detail);
  return detail.map((d: { loc?: unknown[]; msg?: string }) =>
    [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": ")).join("; ");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : describeDetail(body.detail);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const job = (id: string) => `/api/jobs/${encodeURIComponent(id)}`;
const post = (body?: unknown): RequestInit =>
  ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  listJobs: () => request<JobSummary[]>("/api/jobs"),
  getJob: (id: string) => request<JobDetail>(job(id)),
  /** `creator`: the @handle to credit on the clips ("" for none). */
  createJob: (source: string, campaign: string, creator: string) =>
    request<{ id: string; existing: boolean }>("/api/jobs", post({ source, campaign, creator })),
  patchCandidate: (id: string, n: number, patch: CandidatePatch) =>
    request<CandidateView>(`${job(id)}/candidates/${n}`, { method: "PATCH", body: JSON.stringify(patch) }),
  saveWordFixes: (id: string, fixes: Record<string, string>) =>
    request<{ fixes: Record<string, string> }>(`${job(id)}/word-fixes`,
      { method: "PUT", body: JSON.stringify({ fixes }) }),
  render: (id: string, n: number) => request<{ queued: boolean }>(`${job(id)}/candidates/${n}/render`, post()),
  listClips: () => request<RenderedClip[]>("/api/clips"),
  setPosted: (id: string, file: string, posted: boolean) =>
    request<Clip>(`${job(id)}/clips/${encodeURIComponent(file)}/posted`,
      { method: "PUT", body: JSON.stringify({ posted }) }),
  retry: (id: string) => request<{ queued: boolean }>(`${job(id)}/retry`, post()),
  repick: (id: string, force: boolean) => request<{ queued: boolean }>(`${job(id)}/repick`, post({ force })),
  listCampaigns: () => request<CampaignListing[]>("/api/campaigns"),
  reveal: (id: string, file: string) =>
    request<{ revealed: boolean }>(`${job(id)}/reveal/${encodeURIComponent(file)}`, post()),
  /** Sends a dropped video to Clipper, which keeps a copy and says where. `onProgress` gets 0–1.
   *  XMLHttpRequest, not fetch: only it reports how much of a large file has gone. */
  uploadVideo: (file: File, onProgress?: (done: number) => void) =>
    new Promise<{ path: string }>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/uploads?name=${encodeURIComponent(file.name)}`);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress?.(e.loaded / e.total); };
      xhr.onerror = () => reject(new Error("Failed to fetch"));
      xhr.onload = () => {
        let body: { path?: string; detail?: unknown } = {};
        try { body = JSON.parse(xhr.responseText); } catch { /* keep the status text */ }
        if (xhr.status >= 200 && xhr.status < 300 && body.path) resolve({ path: body.path });
        else reject(new ApiError(xhr.status, typeof body.detail === "string" ? body.detail : xhr.statusText));
      };
      xhr.send(file);
    }),
  chooseFile: () => request<{ path: string | null }>("/api/choose-file", post()),
  revealConfig: () => request<{ revealed: boolean }>("/api/config/reveal", post()),
  getSettings: () => request<Settings>("/api/settings"),
  /** Makes this the provider in use. `api_key` left out keeps the saved key. */
  saveSettings: (body: { provider: string; api_key?: string; model?: string }) =>
    request<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  /** The models a key can use; a wrong key is an error, so this is also the key check. */
  listModels: (provider: string, api_key?: string) =>
    request<{ models: string[] }>("/api/settings/models", post({ provider, api_key })),
  setupChecks: () => request<SetupCheck[]>("/api/setup/checks"),
};

const m = (id: string) => `/media/${encodeURIComponent(id)}`;
export const media = {
  proxy: (id: string) => `${m(id)}/proxy.mp4`,
  // version changes when a clip is re-rendered, so a player never mixes old and new bytes
  clip: (id: string, file: string, version: string) =>
    `${m(id)}/clips/${encodeURIComponent(file)}?v=${version}`,
};
