# Control Network — Triage Copilot · Tester Guide

## What this is

An AI copilot that turns a Kubernetes alert into a ready-to-forward incident
report in under a minute. Everything runs locally on your machine and nothing
is stored — close the tab and it's gone.

## Getting started (under a minute)

1. Run `start.bat` (Windows) or `python run.py` (macOS/Linux)
2. Open **http://localhost:8000**
3. Click any incident

**No setup needed.** The app comes with **14 realistic simulated incidents**
already loaded (OOM kills, crash loops, latency spikes, disk pressure, config
errors) — you don't need a Kubernetes cluster, an AI key, or any configuration.
Everything works out of the box.

## What you'll see

- **Incident inbox** (left) — incidents sorted by severity. Simulated ones are
  tagged `SIM`.
- **Evidence table** — measured facts (memory, restarts, logs, recent deploys).
  These are computed, not AI-generated, and appear instantly.
- **Analysis** — streams in on top of the facts: PRIORITY, WHAT HAPPENED,
  ROOT CAUSE, FIX NOW steps, WATCH FOR. Every report says "Advisory only —
  verify before acting."

## What you can do

- **Run a triage** — click an incident or press `Enter`
- **Search & filter** — type in the search box; `sev:critical` filters by
  severity, combinable with text (e.g. `sev:critical payment`)
- **Re-run fresh** — reopening a triaged incident shows the cached report with
  its age; the "Re-run fresh" button gets new data
- **Session history** — "This session · N triages" at the bottom left reopens
  any earlier report instantly (erased when you close the tab)
- **Share the report** — Copy as Markdown, Copy for Slack (pre-formatted),
  Post to Slack, or Export as a .md file
- **Rate it** — thumbs up/down on every report

## Keyboard shortcuts (press `?` in the app)

| Key | Action |
|---|---|
| `j` / `k` or arrows | Navigate incidents |
| `Enter` | Run triage |
| `R` | Re-run fresh (skip cache) |
| `r` | Refresh incident list |
| `c` / `Shift+C` | Copy as Markdown / for Slack |
| `s` | Post to Slack |
| `/` | Focus search |
| `Esc` | Close / blur |
| `?` | This help |

## What we'd love you to test

1. **The 3am test** — pick a critical incident. Is the answer fast, scannable,
   and would you forward it to a client as-is?
2. **The trust test** — can you always tell measured facts apart from AI prose?
3. **Keyboard-only** — run a whole triage without touching the mouse.
4. **Tell us** — thumbs up/down on reports, plus anything that felt slow,
   unclear, or untrustworthy.
