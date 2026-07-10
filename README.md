# Control Network — Kubernetes incident triage

Local-first AI incident triage for Kubernetes. Alert → evidence → verdict. Nothing leaves your network.

## What it does

Control Network receives an alert (Alertmanager webhook at `POST /v1/triage`, or the built-in UI), matches it against known failure patterns, collects read-only evidence from the connectors you have configured (Prometheus, Kubernetes API, GitHub recent PRs, Datadog), compresses that evidence into a bounded token budget, and produces a triage report: deterministic facts with per-fact confidence levels, plus an analysis narrative written by a model you run yourself (Ollama, or any OpenAI-compatible server such as vLLM or LM Studio) or a hosted provider (Anthropic, OpenAI) if you choose to configure one. The report renders in the UI and can be posted to Slack.

The deterministic stages always complete first. If no model is configured, or the model call fails for any reason, the report is generated from a deterministic template instead — the pipeline never depends on an LLM to produce output.

With zero configuration it runs against 15 built-in simulated incidents (`CN_DATA_MODE=sim`), so you can evaluate the full pipeline without a cluster, an API key, or any credentials.

## Quickstart (Docker)

```bash
git clone https://github.com/mihiradvaita-lang/Control-network-Beta.git
cd Control-network-Beta
cp .env.example .env      # all values optional in sim mode
docker compose up
# open http://localhost:8000
```

Send a test alert (simulated OOMKill on a payment service):

```bash
curl -s -X POST http://localhost:8000/v1/triage \
  -H "Content-Type: application/json" \
  -d '{"version":"4","status":"firing",
       "alerts":[{"status":"firing",
         "labels":{"alertname":"KubePodOOMKilled","service":"payment-service","namespace":"prod","severity":"critical"},
         "annotations":{"summary":"payment-service OOMKilled 12 min after deploy v2.3.1"}}]}'
```

On Windows, `.\send-test-alert.ps1` does the same.

## Quickstart (Python, no Docker)

```bash
python run.py     # creates a venv, installs deps, starts the server
```

or `start.bat` on Windows. Then open `http://localhost:8000`.

## Configuration

All settings are environment variables with the `CN_` prefix, set in `.env` (see `.env.example`) or the shell. Everything is optional; unset connectors stay disabled.

| Variable | Default | Purpose |
|---|---|---|
| `CN_ANTHROPIC_API_KEY` | *(empty)* | Enables the Anthropic provider when set |
| `CN_LLM_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model name |
| `CN_LLM_MAX_TOKENS` | `500` | Max tokens for the narrative |
| `CN_LLM_TEMPERATURE` | `0.2` | Sampling temperature |
| `CN_LLM_PROVIDER` | `anthropic` | `anthropic` \| `openai_compatible` \| `ollama` |
| `CN_OPENAI_BASE_URL` | *(empty)* | OpenAI-compatible endpoint (vLLM, LM Studio, LiteLLM, OpenAI) |
| `CN_OPENAI_API_KEY` | *(empty)* | API key for that endpoint |
| `CN_OPENAI_MODEL` | `gpt-4o-mini` | Model name for that endpoint |
| `CN_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama server URL |
| `CN_OLLAMA_MODEL` | `llama3.1` | Ollama model name |
| `CN_SLACK_WEBHOOK_URL` | *(empty)* | Slack Incoming Webhook for `POST /api/slack` |
| `CN_PROMETHEUS_URL` | *(empty)* | Prometheus/Alertmanager base URL; enables the connector |
| `CN_PROMETHEUS_TOKEN` | *(empty)* | Optional bearer token for Prometheus |
| `CN_PROMETHEUS_TIMEOUT` | `3.0` | Prometheus request timeout (seconds) |
| `CN_DATADOG_API_KEY` | *(empty)* | Datadog API key (both keys required to enable) |
| `CN_DATADOG_APP_KEY` | *(empty)* | Datadog application key |
| `CN_DATADOG_SITE` | `datadoghq.com` | Datadog site |
| `CN_DATADOG_TIMEOUT` | `3.0` | Datadog request timeout (seconds) |
| `CN_KUBECONFIG` | *(empty)* | Kubeconfig path; enables read-only K8s evidence (in-cluster auto-detected) |
| `CN_K8S_TIMEOUT` | `5.0` | Kubernetes API timeout (seconds) |
| `CN_GITHUB_TOKEN` | *(empty)* | GitHub token; with `CN_GITHUB_REPO`, enables recent-PR evidence |
| `CN_GITHUB_REPO` | *(empty)* | `owner/repo` for the GitHub connector |
| `CN_GITHUB_TIMEOUT` | `5.0` | GitHub request timeout (seconds) |
| `CN_TOKEN_TARGET` | `800` | Soft token budget for compressed context |
| `CN_TOKEN_HARD_CAP` | `2000` | Hard cap; triggers truncation (flagged in the report) |
| `CN_DATA_MODE` | `sim` | `sim` (15 built-in incidents) \| `prometheus` \| `datadog` |
| `CN_API_TOKEN` | *(empty)* | When set, all write endpoints require `Authorization: Bearer <token>` |
| `CN_CUSTOMER_NAME` | `DemoCorp` | Display name in the UI |
| `CN_ZDR_MODE` | `true` | Zero-data-retention flag, surfaced at `/healthz` |
| `CN_HOST` | `127.0.0.1` | Bind host; loopback-only by default |
| `CN_PORT` | `8000` | Bind port |

## Architecture

Five stages, in order: `match_pattern` (`app/patterns.py`) → `collect` (`app/collectors.py`) → `compress_signals` (`app/compress.py`) → `narrative` (`app/narrative.py`) → `assemble` (`app/report.py`).

Pattern matching and compression are pure local computation and never touch the network. Collection is deterministic in `sim` mode; configured connectors make read-only calls with short timeouts, and any connector failure falls back to sim data with a degraded flag rather than failing the request. The narrative stage is the only stage that can call a model, it runs last, and the deterministic facts are already emitted to the client before it starts. If the provider is unset or the call fails (network, auth, rate limit), a template narrative is used and the response carries a notice: `"AI unavailable — deterministic analysis shown"`.

Version: `0.5.0-pilot`. Test suite: 57 tests, `python -m pytest tests/ -v` (needs `pip install pytest httpx`).

## Security posture

- No data persistence: incidents, evidence, and reports live in RAM for the lifetime of a single request. No database, no incident log on disk. `/healthz` reports `"zdr": true`. The only file the app writes is `skills/specialized.md`, static per-customer config you create explicitly via the onboarding CLI (`python -m app.onboard`) — never incident data.
- Secrets come from environment variables only. Error responses contain only the exception class name — never URLs, keys, or webhook addresses.
- Complete list of outbound destinations, all taken from your `.env`, none hard-coded: your Prometheus/Alertmanager, your Datadog site, your Kubernetes API server, `api.github.com` (if the GitHub connector is enabled), your Slack webhook, and your chosen model endpoint (Anthropic, an OpenAI-compatible URL, or local Ollama). Nothing else.
- The model is read-only: it receives compressed evidence and returns text. It cannot call tools, write to any store, or reach any API.
- Write endpoints require `Authorization: Bearer` when `CN_API_TOKEN` is set; request bodies over 1 MiB are rejected with 413 before parsing; security headers (`CSP`, `X-Frame-Options: DENY`, `X-Content-Type-Options`, `Referrer-Policy`, COOP/CORP) are set on every response, including SSE streams.
- Binds to `127.0.0.1` by default. Docker compose sets `CN_HOST=0.0.0.0` inside the container only; Docker controls external exposure.

The codebase is small enough to audit in an afternoon. Read `app/` before pointing it at anything real.

## Status and feedback

Early beta, public and source-available for evaluation under [LICENSE-EVALUATION.txt](LICENSE-EVALUATION.txt) — sharing the repo is welcome; production or commercial use requires written permission. Feedback and bug reports via GitHub Issues.

`TESTER-GUIDE.md` is the shortest path through a full evaluation; `TESTING_GUIDE.md` is the exhaustive feature checklist; `docs/INTEGRATIONS.md` covers wiring real Alertmanager and Slack.
