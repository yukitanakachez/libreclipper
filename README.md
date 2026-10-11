# LibreClipper

An open-source podcast-to-shorts clipper that runs on your own computer. The app and its
command are called Clipper for short.

![A clip job open in Clipper: the moments it picked on the left, the rendered vertical clip with its headline and word-by-word captions in the phone, and the transcript you trim by clicking words](docs/screenshot.png)

It turns a podcast into vertical clips for TikTok and YouTube Shorts: a video file goes in,
and 1080×1920 MP4s come out with the crop following whoever is
talking, word-by-word captions burned in, an optional headline, a creator credit and
optional background music.

You review the candidate moments before anything renders. Nothing is ever posted for you.

```
file ──► fetch ──► transcribe ──► pick ──► reframe ──► [ you review ]  ──► render ──► MP4s
        (720p     (Whisper,     (Claude   (faces +                        (captions,
         proxy)    on your Mac)  picks)    speaker)                        music, encode)
```

## What it costs to run

Transcription, face tracking and rendering all run locally and are free. The only paid
part is Claude choosing the moments: roughly **$0.25–0.40 per 90-minute episode** with
`claude-opus-5`, or **$0.10–0.15** with `claude-sonnet-5` (set `model` in `config.yaml`).

## Setup

You need an Apple Silicon Mac (M1 or later) and `git`. Then:

```bash
git clone https://github.com/yukitanakachez/libreclipper.git
cd libreclipper
./start
```

That is the whole install. `./start` sets everything up inside the project folder and opens
Clipper in your browser; run it again whenever you want to use Clipper. There is no file to
edit and nothing to export:

- **The first run takes a few minutes.** It downloads Python and the Python packages (about
  1 GB) with [uv](https://docs.astral.sh/uv/), and builds the app's pages (fetching Node.js too
  if you have none). Later runs start in a second or two.
- **The app fetches the rest itself** when it starts: an ffmpeg that can draw captions, and the
  face-detection model. The setup page shows the progress.
- **Your API key goes into the app.** A new install opens on **Set up Clipper**: pick your AI
  provider (Anthropic, OpenAI, Google Gemini and others), paste its key, done. You can change
  it later under **Settings** (the gear in the top bar).
- **The first video is slower**: the speech-to-text model (about 1.5 GB) downloads once, the
  first time something is transcribed.

Everything lands in the project folder (`.venv`, `.tools`, `assets`, `jobs`), so deleting the
folder removes Clipper completely. `./start --port 9000` and `./start --no-browser` work too.

If something looks wrong, `.venv/bin/clipper doctor` lists every check with its fix, and
`.venv/bin/clipper setup` downloads anything missing again.

### Optional settings

Clipper needs no configuration file. To change where jobs and finished clips are kept, how
long working files stay, copy
`config.yaml.example` to `config.yaml` and edit it; every key is optional.

To use your own ffmpeg instead of the downloaded one, set `CLIPPER_FFMPEG` (it must be built
with libass).

### Setting it up by hand

`./start` is a short shell script, and you can do what it does yourself: `uv sync`, then
`cd frontend && npm ci && npm run build`, then `.venv/bin/clipper serve`. On Apple Silicon the
Python must be an arm64 one (`mediapipe` and `mlx-whisper` have no Intel macOS builds), which
is why `./start` brings its own uv and Python rather than trusting the ones on your PATH.

## Using it

```bash
.venv/bin/clipper run ~/Downloads/episode-12.mov --campaign auto
.venv/bin/clipper preview <job-id>          # optional: check the crop before rendering
.venv/bin/clipper approve <job-id> 1 3
.venv/bin/clipper render <job-id>
```

`run` prints the ranked candidates with the reason each was picked; clips flagged
`[check framing]` are ones where the crop fell back to a safe layout. Output lands in
`jobs/<job-id>/out/` as `01-<headline>.mp4` with a matching `.txt` holding the post
caption and hashtags.

Clipper works from video files on your computer. It does not download videos: give it a
link and it will ask for the file instead.

Other commands: `clipper clean` deletes working files from jobs older than
`retention_days` (finished clips are never deleted), and `clipper doctor` re-runs setup
checks.

## Review app

```bash
./start            # opens http://127.0.0.1:8765 (rebuilds the pages first if their source changed)
```

To skip the terminal from then on, make an app once: `.venv/bin/clipper app` puts **Clipper.app**
in `~/Applications`. Opening it starts the server if it isn't running and shows Clipper in its
own window; the server keeps working (rendering, queued jobs) after you close the window. Its log
is `~/Library/Logs/Clipper.log`.

**Settings** (the gear in the top bar; a new install opens on it as **Set up Clipper**). Choose
the one AI provider that picks the moments: Anthropic, OpenAI, Google Gemini, OpenRouter, Mistral,
DeepSeek, or Ollama running on this computer. Paste its API key, press **Check key & list
models** to confirm the key and choose a model, then **Use <provider>**. Only one provider is in
use at a time; the others keep their keys, so switching back needs no retyping. Keys are saved in
`settings.json` next to `config.yaml` (readable only by you, never committed) and are never sent
back to the browser. A key already in your shell (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`, …) is picked up without typing anything. The same page lists what `clipper
doctor` checks on this computer, with the fix for anything missing.

Everything except picking the moments (transcribing, framing, rendering) runs on your computer
whichever provider you choose. Anthropic is the provider Clipper was built and tuned with; the
others go through their OpenAI-compatible APIs.

**The board.** With nothing open you see every clip job as a card, grouped into **Needs you**,
**Working** and **Finished**. Above them, **Next up** names the job that has waited longest for
you (↵ opens it), with tiles for what's working, how many moments are waiting for review and how
many rendered clips you haven't posted yet. The bell in the top bar is an Inbox: jobs ready for
review, finished renders and failures.

**New** (N) starts a job: drop a video onto the big drop area, or click it to pick one in
Finder, then choose a campaign. A video you pick in Finder is read where it is. A dropped
video is copied into `jobs/uploads/` (a browser never says where a dropped file lives), and
that copy is deleted with the job's other working files after `retention_days`.

**A job.** Its moments are listed on the left, best score first. The source video plays in the
iPhone frame. For the selected moment you can:

- trim it by clicking a word in the transcript (start), ⇧-click (end) or double-click (fix its
  spelling). From the keyboard the transcript is one tab stop: ←/→ move a cursor word by word,
  ↵ sets the start, ⇧↵ the end, F2 fixes spelling, ⌘Z undoes a trim;
- change its headline, post caption, layout and music;
- **Render** (⌘↵) it.

Every moment renders on its own: press Render on the ones you want, in any order, and they are
made one at a time while you keep working on the others. When a clip is done, the **Rendered**
tab under the phone plays it, and under the Render button you get **Mark posted**, **Copy
caption** and **Show in Finder**. **Render again** replaces the clip (the earlier file moves to
`previous/`) and it counts as not posted again. **Pick again…** asks Claude for a fresh set of
moments; clips you already rendered are kept.

**Rendered** (top bar) lists every rendered clip of every job, newest first, under **Not
posted**, **Posted** and **All**. Each card plays the clip and has the same three buttons, so
after you upload one, **Mark posted** is one click; click it again to undo. Back in the job, a
posted moment gets a green check and tint in the list, so you can see what's left. The number next to
Rendered in the top bar is how many clips are still waiting to be posted. Clipper never posts
anything itself: the mark is your own record, kept in each job's `clips.json`.

**Shortcuts** (ignored while typing in a field or while a dialog is open):

| keys | does |
|---|---|
| J / K | next / previous job on the board, or moment in a job |
| ↵ | open (Next up, or the focused job) |
| ⌘↵ | render the selected moment |
| ⌘Z | undo trim |
| N | new |
| ? | show this list |

The server listens on 127.0.0.1 only and runs one step at a time; its queue survives a restart.

## Campaigns

One YAML file per creator in `campaigns/`, applied to every clip from that creator:

```yaml
name: Example Podcast
credit: { enabled: true, handle: "@examplepod", position: below_headline }
clip_length: { min: 20, max: 60 }
required_hashtags: ["#examplepod"]
vocabulary: ["Jane Doe", "Acme"]     # spelling hints for Whisper
headline: { enabled: true }
music: { allowed: true, folder: music/example-podcast, volume_db: -22 }
captions: { accent_color: "#FFE500", uppercase: false }
pacing: { cut_pauses: true, max_pause: 0.3, speed: 1.1 }
```

`vocabulary` is worth filling in: it is what stops guest names being misspelled in
burned-in captions.

`pacing` tightens the rhythm: silences longer than `max_pause` seconds are cut down to a
short breath, then the clip plays at `speed` (pitch preserved). Both are on by default; set
`cut_pauses: false` and `speed: 1.0` for campaigns that forbid altering the creator's audio.
`clip_length` limits apply to the finished clip, after cuts and speed-up.

To re-pick moments on a job you already transcribed (after changing the prompt or campaign,
say): `clipper run <file> --campaign <slug> --from pick`.

## How a job is stored

Each video gets `jobs/<job-id>/`, and every step writes one file:

| File | Written by | Holds |
|---|---|---|
| `status.json` | all | current step, progress, any error |
| `meta.json` | fetch | title, channel, duration, resolution |
| `proxy.mp4` | fetch | 720p working copy (never the final output) |
| `transcript.json` | transcribe | every word with its timing |
| `candidates.json` | pick | the moments, your edits, approval flags |
| `crop_plan.json` | reframe | where the 9:16 crop goes, moment by moment |
| `out/` | render | finished clips and their post captions |
| `clips.json` | review app | which moment each clip came from, and when you marked it posted |

Any step can be re-run without redoing the ones before it, and every file is plain JSON
you can open.

## Other systems

Clipper is built and tested on Apple Silicon Macs. `./start` also runs on Linux (x86-64 and
arm64), where transcription switches to `faster-whisper` by itself; that path has had far less
use, so expect rough edges. An NVIDIA GPU makes transcription much faster there.

Windows has no launcher yet. Under WSL, use the Linux steps. Natively you would need to install
uv, Node.js and an ffmpeg with libass yourself, then follow "Setting it up by hand" above; the
**Choose file…** button and **Show in Finder** are Mac-only.

## Tests

```bash
.venv/bin/clipper setup             # once: the render tests use the downloaded ffmpeg
.venv/bin/python -m pytest          # fast, no network, no API calls
.venv/bin/python -m pytest -m live  # opt-in: real Claude API call, costs a few cents
```

The end-to-end test renders a real clip with real ffmpeg and checks the output is
1080×1920 at −14 LUFS. It skips itself if the fixture video, font or libass is missing;
generate the fixture with `python tests/fixtures/make_fixtures.py`.

## Before trusting it on real work

`scripts/validate_speaker.md` is a short procedure for checking speaker detection against
four real episodes. It is the least certain part of the design, and the file lists which
knobs to turn if it does not hold up.

## Credits

- Captions are set in [Montserrat](https://github.com/JulietaUla/Montserrat), under the SIL
  Open Font License (`assets/fonts/OFL.txt`).
- Video work is done by [FFmpeg](https://ffmpeg.org); Clipper downloads a static build from
  [ffmpeg.martin-riedl.de](https://ffmpeg.martin-riedl.de) rather than shipping one. That build
  is GPL-licensed and is a separate program, not part of Clipper.
- Speech-to-text is [Whisper](https://github.com/openai/whisper) through mlx-whisper or
  faster-whisper; faces are found with Google's [MediaPipe](https://developers.google.com/mediapipe)
  face landmarker.
- The provider marks on the Settings page come from [Simple Icons](https://simpleicons.org)
  (CC0). The names and logos belong to their owners and are shown only to identify each
  service; Clipper is not affiliated with or endorsed by any of them.

## License

MIT: see [LICENSE](LICENSE). Security notes are in [SECURITY.md](SECURITY.md), and
[CONTRIBUTING.md](CONTRIBUTING.md) says how to send a change.

## Legal note

Clip only videos you own or have the creator's permission to clip. Clipper does not download
videos from YouTube or anywhere else: you bring the file.
