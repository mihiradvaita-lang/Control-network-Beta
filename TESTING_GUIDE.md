# Control Network — Beta Testing Guide

Complete feature checklist for the private beta. Each item includes the exact command or
action to exercise it. Prerequisites: server running (`docker compose up` or `python run.py`).

---

## Prerequisites

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — at minimum, set CN_API_TOKEN if you want auth testing
# (leave everything else commented out for zero-config sim mode)

# 2. Start the server
docker compose up          # Docker path (recommended)
# OR
python run.py              # direct Python path

# 3. Confirm the server is up
curl http://localhost:8000/healthz
```

---

## Feature Checklist

### ✅ 1. Health endpoint
```bash
curl http://localhost:8000/healthz
# Expected: {"status":"ok","version":"0.4.0-mvp","zdr":true,"llm_provider":"deterministic",...}
```
**Pass criteria:** HTTP 200, `status == "ok"`, `zdr == true`.

---

### ✅ 2. Auth rejection (only when CN_API_TOKEN is set)
```bash
# First, set CN_API_TOKEN=my-secret-token in .env and restart the server.
# Then test WITHOUT the token:
curl -s -X POST http://localhost:8000/v1/triage \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"labels":{"alertname":"test"}}]}'
# Expected: HTTP 401  {"error":"unauthorized"}

# And WITH the token:
curl -s -X POST http://localhost:8000/v1/triage \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-secret-token" \
  -d '{"alerts":[{"labels":{"alertname":"KubePodOOMKilled","pod":"payment-svc-abc123-x2k9p"}}]}'
# Expected: HTTP 200 with report_markdown
```
**Pass criteria:** No-token → 401. Correct token → 200 with a report.

**Note:** If `CN_API_TOKEN` is NOT set in `.env`, auth is disabled and all requests are accepted.

---

### ✅ 3. Simulated incident list (14 scenarios)
```bash
curl http://localhost:8000/api/scenarios
# Expected: {"scenarios":[...14 items...],"customer":"DemoCorp"}
```
Or open **http://localhost:8000** in a browser — the inbox loads all 14 scenarios.

**Pass criteria:** 14 scenarios visible; each has `id`, `alertname`, `severity`, `service`.

---

### ✅ 4. Alert ingestion via Alertmanager v4 webhook (`POST /v1/triage`)
```bash
curl -s -X POST http://localhost:8000/v1/triage \
  -H "Content-Type: application/json" \
  -d '{
    "version": "4",
    "status": "firing",
    "receiver": "control-network",
    "commonLabels": {"alertname": "KubePodOOMKilled", "severity": "critical",
                     "namespace": "prod", "cluster": "eks-prod-use1"},
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "KubePodOOMKilled", "namespace": "prod",
                 "pod": "payment-svc-7d9f8c6b5-x2k9p", "severity": "critical"},
      "annotations": {"summary": "Pod payment-svc was OOMKilled"},
      "fingerprint": "abc123def456"
    }]
  }'
# Expected: {"incident_id":"abc123def456","pattern":"OOMKill","report_markdown":"## Incident Report: ..."}
```
**Pass criteria:** HTTP 200, `pattern == "OOMKill"`, `report_markdown` contains `"Advisory only"`.
Pod hash is stripped: `payment-svc-7d9f8c6b5-x2k9p` → `payment-svc` in the report.

---

### ✅ 5. SSE triage stream (`GET /api/triage/stream`)
```bash
curl -N "http://localhost:8000/api/triage/stream?scenario_id=oom-payment-001"
# Expected: SSE frames in order:
# event: phase    data: {"phase":"DETECTED",...}
# event: phase    data: {"phase":"CORRELATING",...}
# event: meta     data: {...}
# event: facts    data: {"pattern":"OOMKill","facts":[...],...}
# event: phase    data: {"phase":"ANALYZING",...}
# event: token    data: {"t":"..."} (one or more)
# event: phase    data: {"phase":"DONE",...}
# event: done     data: {"report_markdown":"...","llm":"deterministic",...}
```
**Pass criteria:** Events arrive in order; `facts` appears before any `token`; `done` is last.
Median latency to first `facts` event: ~4 ms (deterministic mode).

---

### ✅ 6. Non-streaming triage (`POST /api/triage`)
```bash
curl -s -X POST http://localhost:8000/api/triage \
  -H "Content-Type: application/json" \
  -d '{"scenario_id": "crashloop-checkout-api-001"}'
# Expected: full JSON response with report_markdown in one shot
```

---

### ✅ 7. LLM verdict generation — Anthropic (cloud)
Set in `.env`:
```env
CN_ANTHROPIC_API_KEY=sk-ant-...
CN_LLM_MODEL=claude-haiku-4-5-20251001
CN_LLM_PROVIDER=anthropic
```
Restart the server, then trigger a triage. The `done` event will show `"llm":"anthropic"` instead of
`"deterministic"`. The narrative section will be AI-generated prose rather than the deterministic template.

**Pass criteria:** `/healthz` shows `"llm_provider":"anthropic"`; triage `done` event has `"llm":"anthropic"`.

---

### ✅ 8. LLM verdict generation — Ollama (local)
```env
CN_LLM_PROVIDER=ollama
CN_OLLAMA_BASE_URL=http://localhost:11434
CN_OLLAMA_MODEL=llama3.1
```
Start Ollama separately (`ollama serve`), pull the model (`ollama pull llama3.1`), then restart
the server and run a triage.

**Pass criteria:** `/healthz` shows `"llm_provider":"ollama"`; `done.llm == "ollama"`.

---

### ✅ 9. Deterministic fallback (no API key)
Leave `CN_ANTHROPIC_API_KEY` unset (the default). Run any triage.

**Pass criteria:** Report is complete; `done.llm == "deterministic"`; no error in the stream.
The `"Advisory only"` disclaimer is always present regardless of LLM mode.

---

### ✅ 10. Prometheus Alertmanager integration (live alerts IN)
```env
CN_DATA_MODE=prometheus
CN_PROMETHEUS_URL=http://your-alertmanager:9093
```
The incident inbox will show live alerts from Alertmanager instead of simulated ones.
Each alert is tagged with `"platform":"prometheus"`.

**Pass criteria:** `GET /api/incidents` returns `{"incidents":[...],"source":"live"}`.

---

### ✅ 11. Datadog integration (live triggered monitors)
```env
CN_DATADOG_API_KEY=...
CN_DATADOG_APP_KEY=...
```
Live Datadog monitor alerts appear in the incident inbox tagged `"platform":"datadog"`.

---

### ✅ 12. Slack posting
With `CN_SLACK_WEBHOOK_URL` set in `.env`:
```bash
# Using the UI: press 's' on a triaged incident
# OR via API:
curl -s -X POST http://localhost:8000/api/slack \
  -H "Content-Type: application/json" \
  -d '{"scenario_id": "oom-payment-001"}'
# Expected: {"configured":true,"ok":true,"status":200}
```
Without `CN_SLACK_WEBHOOK_URL`:
```bash
# Expected: {"configured":false}  — UI shows copy-to-clipboard toast instead
```
**Pass criteria:** With webhook → Slack message appears in your channel.
Without webhook → `{"configured":false}` with no error.

---

### ✅ 13. Secret redaction in logs / error responses
The server never logs or echoes secrets (API keys, webhook URLs, tokens).
```bash
# Force a Slack error and verify the webhook URL isn't leaked:
# Set CN_SLACK_WEBHOOK_URL to an invalid URL, trigger POST /api/slack.
# Expected response body: {"configured":true,"ok":false,"status":0,"error":"ConnectError"}
# The error field is ONLY the exception class name, never the URL.
```
**Pass criteria:** Error responses contain only the exception type name; no URLs, keys, or tokens.

---

### ✅ 14. Prometheus metrics endpoint
```bash
curl http://localhost:8000/metrics
# Expected:
# # Control Network metrics
# cn_triage_total 0
# cn_triage_errors 0
# cn_feedback_total 0
# cn_slack_posts 0
```
Run a triage, then re-check — `cn_triage_total` increments.

---

### ✅ 15. Feedback API (in-RAM ring buffer)
```bash
curl -s -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"incident_id":"oom-payment-001","vote":"up","note":"clear and accurate"}'
# Expected: {"ok":true}

# Vote must be "up" or "down":
curl -s -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"incident_id":"i","vote":"maybe"}'
# Expected: HTTP 422 (validation error)
```

---

### ✅ 16. Platform status endpoint
```bash
curl http://localhost:8000/api/platforms
# Expected: {"prometheus":{"configured":false,...},"datadog":{"configured":false,...},"any_live":false}
```

---

### ✅ 17. Keyboard-only navigation (browser)
Open **http://localhost:8000**. Without touching the mouse:
- `j`/`k` or arrows: move selection in the incident inbox
- `Enter`: run triage on selected incident
- `c`: copy report as Markdown
- `s`: post to Slack
- `/`: focus search box (try `sev:critical payment`)
- `Esc`: blur search
- `?`: toggle keyboard shortcut help

---

### ✅ 18. Security headers on all responses
```bash
curl -v http://localhost:8000/healthz 2>&1 | grep -i "x-content-type\|x-frame\|csp\|referrer"
# Expected: all security headers present on JSON, static, and SSE responses
```

---

### ✅ 19. Body-size guard (413 on oversized payload)
```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/v1/triage \
  -H "Content-Type: application/json" \
  -H "Content-Length: 1048577" \
  -d '{}'
# Expected: 413
```

---

### ✅ 20. Automated smoke test
```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh
# With DRY_RUN (no Slack needed):
DRY_RUN=1 ./scripts/smoke_test.sh
```

---

## NOT IMPLEMENTED — Do not test these

The following features are **present in configuration/code as placeholders** but are
**NOT functional** for this beta. Treating failures here as bugs is incorrect.

| Feature | Status | Notes |
|---|---|---|
| Kubernetes collector | **NOT IMPLEMENTED** | Requires a live K8s cluster with `kubeconfig` or in-cluster auth. The code exists but has no test coverage against a real cluster. |
| GitHub collector | **NOT IMPLEMENTED** | Requires `CN_GITHUB_TOKEN` + `CN_GITHUB_REPO`. No cluster-level "recent deploys" correlation available in sim mode. |
| `CN_DATA_MODE=real` | **NOT IMPLEMENTED** | The `real` value for `CN_DATA_MODE` is referenced in docs but has no distinct behavior (sim mode is used regardless). Use `prometheus` or `datadog` for live data. |
| Onboarding CLI (`python -m app.onboard`) | **NOT TESTED** | The interactive interview writes `skills/specialized.md`; it has not been tested end-to-end in this beta build. |

---

## Full Test Suite

```bash
pip install pytest httpx respx
python -m pytest tests/ -v
# Expected: all tests pass in deterministic mode (no API key required)
```

---

## Known Limitations

- **No persistence:** reports disappear on server restart; session history is tab-local.
- **14 fixed scenarios:** sim mode uses the same 14 scenarios every time; no randomization.
- **Single-user:** no multi-user isolation; all users share the same in-RAM feedback buffer.
- **ZDR:** zero data retention is a design goal; verify via `/healthz` → `"zdr":true`.
