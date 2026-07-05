# Control Network — Kubernetes Incident Triage Copilot

A local-first triage copilot for Kubernetes incidents: alert → pattern match → collect
signals → compress → narrative (AI or deterministic) → markdown report. Ships with 14
simulated incidents (no real cluster needed — `CN_DATA_MODE=sim`) so you can try the whole
flow in under a minute.

> **Private beta.** See the [NOTICE](#notice) at the bottom before sharing access.

**Latency philosophy: deterministic-first.** Pattern matching, signal collection, and
evidence compression are pure, fast, local computation — they are always emitted to the
client *before* any model call starts. If the model is slow, unreachable, or not configured,
you still get a complete, correct report built from a deterministic template. AI narrative is
additive context layered on top of facts you already have — it is never a prerequisite for a
usable report.

**Zero-retention.** Everything lives in RAM for the lifetime of a single request. There is no
database and no on-disk incident/report log. The only files this app writes to disk are
static setup config you create yourself (`skills/specialized.md` via the onboarding CLI) —
never incident data.

## Quickstart (Docker — recommended)

```bash
git clone <repo-url>
cd CN-MVP
cp .env.example .env          # edit .env to fill in values (all optional for sim mode)
docker compose up             # builds and starts the server
# open http://localhost:8000
./scripts/smoke_test.sh       # verify the full pipeline (DRY_RUN=1 if Slack not configured)
```

No API key is required — the app runs in deterministic (template) mode with zero configuration.
To enable AI-written narratives, set `CN_ANTHROPIC_API_KEY` (or a BYO-model provider) in `.env`
and restart with `docker compose up`.

## Quickstart (Python — no Docker)

```bash
python run.py        # macOS/Linux/Windows — creates a venv, installs deps, starts the server
```

or on Windows:

```
start.bat
```

Then open `http://localhost:8000`.

## Environment variables

All variables use the `CN_` prefix and can be set in `.env` (see `.env.example`) or the shell.

| Variable | Default | Purpose |
|---|---|---|
| `CN_ANTHROPIC_API_KEY` | *(empty)* | Enables the Anthropic provider when set |
| `CN_LLM_MODEL` | `claude-3-5-haiku-20241022` | Anthropic model name |
| `CN_LLM_MAX_TOKENS` | `500` | Max tokens for the narrative |
| `CN_LLM_TEMPERATURE` | `0.2` | Sampling temperature |
| `CN_LLM_PROVIDER` | `anthropic` | `anthropic` \| `openai_compatible` \| `ollama` |
| `CN_OPENAI_BASE_URL` | *(empty)* | Base URL for an OpenAI-compatible endpoint |
| `CN_OPENAI_API_KEY` | *(empty)* | API key for the OpenAI-compatible endpoint |
| `CN_OPENAI_MODEL` | `gpt-4o-mini` | Model name for the OpenAI-compatible endpoint |
| `CN_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server URL |
| `CN_OLLAMA_MODEL` | `llama3.1` | Ollama model name |
| `CN_SLACK_WEBHOOK_URL` | *(empty)* | Slack Incoming Webhook URL for `POST /api/slack` |
| `CN_TOKEN_TARGET` | `800` | Soft token budget for compressed context |
| `CN_TOKEN_HARD_CAP` | `2000` | Hard token cap; triggers truncation |
| `CN_DATA_MODE` | `sim` | `sim` (14 demo incidents), `prometheus`, or `datadog`; `real` is **NOT IMPLEMENTED** |
| `CN_API_TOKEN` | *(empty)* | When set, all write endpoints require `Authorization: Bearer <token>` |
| `CN_CUSTOMER_NAME` | `DemoCorp` | Display name shown in the UI |
| `CN_ZDR_MODE` | `true` | Zero-data-retention flag surfaced in `/healthz` |
| `CN_HOST` | `0.0.0.0` | Bind host |
| `CN_PORT` | `8000` | Bind port |

If no provider is enabled (no key/base URL reachable, or the live call fails for any reason —
network, auth, rate limit), the app **automatically falls back to a deterministic narrative**
and surfaces a `notice` event in the stream (`"AI unavailable — deterministic analysis
shown"`) — the report is still generated and the request never fails.

## Endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/scenarios` | List the 14 simulated incidents |
| `POST /api/triage` | Non-streaming triage for a `scenario_id` or embedded `incident` |
| `GET /api/triage/stream?scenario_id=...` | SSE stream: `phase` → `meta`/`facts` → `token`(s) → [`notice`] → `phase(DONE)` → `done` |
| `POST /v1/triage` | Webhook-style ingestion — accepts a Prometheus Alertmanager v4 body, the legacy `{"alerts":[...]}` shape, or `{"incident": {...}}` |
| `POST /api/slack` | Posts a just-computed report to Slack (`{"scenario_id"}` or `{"incident_id"}`); returns `{"configured": false}` if no webhook is set |
| `GET /api/specialized/template` | Raw text of the `specialized.md` template |
| `POST /api/feedback` | Thumbs up/down feedback, kept in an in-RAM ring buffer |
| `GET /healthz` | Status, version, ZDR flag, active LLM provider (or `deterministic`) |
| `GET /metrics` | Plaintext counters |

## Architecture

`alert → match_pattern → collect signals → compress_signals → stream_narrative (AI or
deterministic) → assemble (markdown report)` — the deterministic stages (`app/patterns.py`,
`app/collectors.py`, `app/compress.py`) never touch the network; only `app/narrative.py`'s
provider calls do, and they are the last thing to run.

## Tests

```bash
pip install pytest httpx
python -m pytest tests/ -v
```

## Onboarding a real customer (specialized.md)

```bash
python -m app.onboard
```

Runs a ~30-minute interactive interview and writes `skills/specialized.md` (per-customer
investigation logic — environment fingerprint, known failure patterns, escalation map, tone
preferences, do-not-do list). This is injected into the AI prompt as **data**, never as
instructions. The blank template lives at `skills/specialized.template.md` and is also
served at `GET /api/specialized/template`.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `j` / `k` or `↓` / `↑` | Move selection in the incident inbox |
| `Enter` | Run triage on the selected incident |
| `c` | Copy the current report to the clipboard |
| `s` | Post the current report to Slack |
| `/` | Focus the inbox search/filter box |
| `Esc` | Blur the search box / close the help overlay |
| `?` | Toggle the keyboard-shortcut help overlay |

See `docs/INTEGRATIONS.md` for wiring up real Alertmanager and Slack.
See `TESTING_GUIDE.md` for a complete feature checklist with exact commands.

## Not Implemented (beta)

The following configuration options appear in `.env.example` but are **not functional** in
this beta build — do not mistake missing behavior for bugs:

| Feature | Status |
|---|---|
| Kubernetes collector (`CN_KUBECONFIG`) | **NOT IMPLEMENTED** — requires a live K8s cluster |
| GitHub collector (`CN_GITHUB_TOKEN`) | **NOT IMPLEMENTED** — requires token + repo configured |
| `CN_DATA_MODE=real` | **NOT IMPLEMENTED** — use `prometheus` or `datadog` for live data |

## Security Posture

- **Token-protected write endpoints:** when `CN_API_TOKEN` is set in `.env`, all `POST`/`PUT`/`PATCH`
  endpoints require `Authorization: Bearer <token>`; no token → HTTP 401.
- **No secrets logged:** error responses contain only the exception class name, never URLs, keys, or
  webhook addresses. All secrets are read from environment variables only.
- **Outbound URLs from env config only:** the app calls Anthropic/OpenAI/Ollama/Slack/Prometheus/Datadog
  only at addresses you provide in `.env`; no hard-coded external calls.
- **LLM is read-only:** the model receives compressed, anonymized evidence; it never writes to any
  store, API, or file.
- **No data persisted:** everything lives in RAM for the lifetime of a single request. No database,
  no incident log, no disk writes of incident data. (`/healthz` → `"zdr":true` confirms this.)
- **Nothing leaves your network** beyond the outbound calls you explicitly configure.
- **Loopback by default:** the server binds to `127.0.0.1` unless `CN_HOST=0.0.0.0` is set;
  Docker compose sets `CN_HOST=0.0.0.0` inside the container (Docker handles external port mapping).

---

## NOTICE

This is a **private beta** provided for evaluation purposes only. Access is granted under the
terms of the [LICENSE](LICENSE) file:

- Do **not** share this repository, source code, or your access credentials with anyone who is
  not an authorized beta participant.
- Do **not** use this software in production or commercially without written permission.
- Feedback and bug reports are welcome — please send them directly to the team rather than
  filing public issues.
