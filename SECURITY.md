# Security

LibreClipper (the app calls itself Clipper) runs entirely on your own computer. A few things worth knowing:

- **The app is local only.** `clipper serve` listens on `127.0.0.1` and refuses requests
  that come from other websites or other host names. Don't put it behind a public address:
  it has no sign-in.
- **API keys are stored in plain text** in `settings.json` in the project folder, readable
  only by your user account and ignored by git. They are sent only to the provider you chose,
  and never back to the browser (the page sees the last four characters). Anyone who can read
  your files can read them, so use a key you can revoke.
- **Downloads are pinned.** The ffmpeg build and the face-detection model that Clipper fetches
  for itself are fixed versions checked against SHA-256 values in `clipper/provision.py`.
  `./start` installs uv from astral.sh and, if needed, Node.js from nodejs.org.
- **Your videos stay on your computer.** Only the transcript of a video is sent to the AI
  provider, to pick the moments.

## Reporting a problem

Please report security problems privately through GitHub's "Report a vulnerability" button
(the repository's Security tab) rather than a public issue. Include what you did, what
happened, and your system. You should hear back within a week.
