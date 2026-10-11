# Contributing

Thanks for wanting to help. LibreClipper is a small project; small, focused pull requests are the
easiest to review.

## Getting set up

`./start` once (see the README) gives you everything: `.venv` with the Python packages, the
built frontend, ffmpeg and the face model.

## Before you open a pull request

```bash
.venv/bin/python -m pytest                      # Python tests: no network, no API calls
cd frontend && npm ci && npm test && npm run lint && npm run build
```

Both must pass. The render tests skip themselves until you have made the fixture video once:
`.venv/bin/python tests/fixtures/make_fixtures.py`.

`.venv/bin/python -m pytest -m live` makes one real, paid call to your AI provider; run it
when you change `clipper/pick.py`, `clipper/providers.py` or the prompt.

## What goes where

- `clipper/` is the pipeline: one module per step (`fetch`, `transcribe`, `pick`, `reframe/`,
  `render`), driven by `pipeline.py`. Every step reads and writes plain JSON in the job folder.
- `clipper/web/` is the local API the app talks to; the rules live in `review.py`.
- `frontend/` is the app (React, TypeScript, Vite).
- `campaigns/` holds per-creator settings. Only `auto.yaml` and `example.yaml` are tracked;
  your own campaign files stay on your computer.

## Ground rules

- Add or update a test with every behaviour change.
- Keep words on screen plain: say what happened and what to do next.
- Never commit keys, `settings.json`, `config.yaml`, or anything from `jobs/`.
- New AI providers go in the table at the top of `clipper/providers.py`; anything that speaks
  the OpenAI chat-completions dialect is a few lines.
