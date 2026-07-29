# Recording the demo

The README leads with a placeholder because no recording exists yet — the
machine this was built on never had Docker installed, so the stack has never
run. This file is everything needed to produce the recording once it does.

Target: **90 seconds or less**, silent, looping. A reviewer watches it before
they read anything.

## Before you start

```bash
cp .env.example .env
make up
docker compose run --rm ingest-api alembic upgrade head
```

Wait for all six containers to report healthy:

```bash
docker compose ps
```

Then let it idle for **at least thirty seconds** before recording. Two reasons:
the scorer needs 20 samples per device before it produces any score at all, and
you want the fleet visibly calm and all-NORMAL before anything happens. If any
device is showing WATCH or ALERT on an untouched fleet, something is wrong —
stop and check the logs rather than recording it.

Set the browser to **1280×800** and use dark mode (the page commits to dark).
Close other tabs so the SSE connection is not competing for the browser's
per-origin connection limit.

## Shot list

| Time | What is on screen |
| ---- | ----------------- |
| 0:00–0:08 | Whole console at rest. Four devices, all NORMAL, scores low, CRM panel empty. Let it sit — the reviewer needs to register "calm" before "alarm". |
| 0:08–0:12 | Cursor moves to **Inject Fault**. Click. |
| 0:12–0:20 | Sensor trace bends. Degradation score starts climbing on the right axis. |
| 0:20–0:24 | Badge flips NORMAL → WATCH. |
| 0:24–0:30 | Badge flips WATCH → ALERT, **and the ticket appears in the CRM panel**. This is the shot the whole repository exists for — do not cut away early. |
| 0:30–0:40 | Slow zoom or pause on the ticket: device ID, `F1-07`, severity. |
| 0:40–0:55 | Click a healthy device in the fleet list to show it is still NORMAL — the fault is scoped to one unit, not the whole fleet. |
| 0:55–1:05 | Optional: click **Reset**, show the fleet returning to calm. |

If the ALERT takes noticeably longer than ten seconds, do not speed up the
recording to hide it. Something has regressed, and the acceptance test should
have caught it — run it and find out why:

```bash
cd apps/ingest-api && pytest tests/integration -v
```

## Tooling

Free options, in rough order of least effort:

- **ScreenToGif** (Windows) — records straight to an optimised GIF, has a
  built-in editor for trimming and cropping.
- **OBS Studio** (any platform) — record MP4, then convert.
- **macOS** — ⇧⌘5 records to MOV.

For MP4 or MOV, convert with a palette pass or the file will be both large and
ugly:

```bash
ffmpeg -i demo.mov -vf "fps=12,scale=1200:-1:flags=lanczos,palettegen" palette.png
ffmpeg -i demo.mov -i palette.png -lavfi "fps=12,scale=1200:-1:flags=lanczos [x]; [x][1:v] paletteuse" docs/diagrams/demo.gif
```

12 fps is enough for a dashboard and roughly halves the file against 24. Keep
the result **under 10 MB** — GitHub will render it, but a reviewer on a phone
will not wait for 40 MB.

An MP4 uploaded directly to the GitHub release or issue tracker and linked from
the README is a reasonable alternative: it plays inline, it is smaller, and it
supports a scrub bar.

## Putting it in the README

Save as `docs/diagrams/demo.gif`, then replace the placeholder block near the
top of the README with:

```markdown
![Inject Fault: NORMAL to ALERT to an open support ticket in under ten seconds](docs/diagrams/demo.gif)
```

Write real alt text, as above. A reviewer with images disabled, and every
screen reader, gets only that sentence.

Delete the warning block when you do. Leaving both is worse than either.
