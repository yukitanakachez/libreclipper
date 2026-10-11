# Speaker-detection validation

A short procedure for checking speaker detection against real episodes. It is the least
certain part of the design: everything else is deterministic, but "who is talking" is
inferred from mouth movement.

## Procedure

1. Pick 4 real episodes with different setups: two-person with cuts between cameras,
   two-person locked wide shot, three or more people, one solo.
2. For each: `.venv/bin/clipper run <file> --campaign <slug> --stop-after reframe`
3. `.venv/bin/clipper preview <job-id>` writes `jobs/<id>/work/preview_NN.mp4` per candidate.
4. Watch each preview and record, per clip:
   - Was the crop on the person actually talking? (yes / mostly / no)
   - Any switch that felt jumpy or late?
   - Did anyone get cut in half or pushed out of frame?
5. Record the results in the table below, with the date and episode URLs.

## Decision rule

If "yes" is below 3 of 4 episodes for the two-person cases, change the default for
2-face shots from Speaker to Stack in `clipper/reframe/layout.py` (`choose_layout`);
audio diarization would be the next thing to try.

Knobs worth trying before giving up on speaker mode, all in
`clipper/reframe/speaker.py`:

| Symptom | Knob |
|---|---|
| Crop switches too eagerly | raise `MIN_HOLD` (1.5s) or `MARGIN` (0.15) |
| Crop is late to the new speaker | lower `MIN_HOLD` |
| Crop sticks to the wrong person in a wide shot | raise `CONFIDENT_SCORE` in `plan.py` so it falls back to Stack |
| Brief flashes on a different face | raise `MIN_SPAN` (0.4s) |

## Results

| Date | Episode | Setup | Crop on speaker | Jumpy switches | Framing problems |
|------|---------|-------|-----------------|----------------|------------------|
| 2026-09-23 | [Jubilee — Hot Takes](https://www.youtube.com/watch?v=Thb1y2nIMic) (65 min) | 3+ people, editor cuts to whoever talks | n/a — Speaker mode ran on 4 of 125 shots; does not count toward the pass rule | none seen | 48 of 125 shots fell back to Fit; many are one person in a medium/wide shot (see note) |

### Notes

**Jubilee — Hot Takes (2026-09-23).** Layout census over all 6 candidates: 73 shots
Single (one face), 4 Speaker (two faces, all confident), 48 Fit, 0 with three or more
faces. Of the 48 Fit shots, 33 had no face detected at all and 15 had a face in fewer
than 5 samples. Close-up Single crops frame well. The group wide shots are correctly
Fit, but for the wrong reason: zero faces found, not three or more.

The Fit fallbacks on one-person medium and wide shots are a **detection-range**
problem, not a speaker problem. The landmarker's face detector is tuned for close-ups:
at 94.8 s and 89.9 s it finds no face in the full frame but does find one in a 2x
centre zoom of the same frame. Not fixed yet: a good first issue for anyone who wants
to improve framing.
