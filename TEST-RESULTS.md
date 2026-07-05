# Control Network — Test & Verification Results

Date: 2026-06-30 (test run). Mode: deterministic (no `CN_ANTHROPIC_API_KEY` / no BYO-model env
vars set — confirms the no-network fallback path end-to-end).

## pytest

```
6 passed in 0.24s
```

Tests: `test_all_scenarios_triage`, `test_zdr_scrub`, `test_facts_event_present_and_ordered_before_token_and_done`,
`test_phase_events_in_order`, `test_graceful_degradation_on_provider_failure`,
`test_all_scenarios_have_evidence_and_analysis_sections`.

## Per-scenario latency (ms), deterministic mode

Measured client-side with a plain Python/urllib script hitting
`GET /api/triage/stream?scenario_id=...` and timing arrival of the `facts` and `done` SSE
frames from request start (`time.monotonic()`).

| scenario_id | facts_ms | done_ms |
|---|---:|---:|
| oom-payment-001 | 11.59 | 15.45 |
| oom-postgres-replica-001 | 3.93 | 7.35 |
| crashloop-checkout-api-001 | 3.86 | 9.66 |
| crashloop-notifications-worker-001 | 3.79 | 7.19 |
| latency-api-gateway-001 | 3.42 | 7.04 |
| latency-orders-service-001 | 3.68 | 7.06 |
| diskpressure-postgres-001 | 3.54 | 7.27 |
| configerror-api-gateway-001 | 4.01 | 7.66 |
| configerror-checkout-service-001 | 4.38 | 7.70 |
| oom-billing-api-payments-001 | 3.34 | 7.16 |
| crashloop-kafka-consumer-prod-002 | 3.43 | 7.44 |
| latency-search-service-prod-003 | 4.18 | 7.71 |
| pv-redis-prod-004 | 4.17 | 8.08 |
| configerr-billing-api-payments-005 | 3.63 | 6.98 |

**Summary:**
- `facts` event: min = 3.34 ms, median = 3.82 ms, max = 11.59 ms (first request pays a one-time
  interpreter/JIT warm-up cost; steady-state is ~3.3–4.4 ms)
- `done` event: min = 6.98 ms, median = 7.40 ms, max = 15.45 ms

This confirms the deterministic-first latency contract: evidence facts are on the wire in
single-digit milliseconds, well before any narrative work, and the full report (deterministic
narrative + evidence) completes in under 16 ms even in the worst (cold-start) case.

## Verified SSE event order

Captured from a real run against `oom-payment-001`:

```
event: phase        data: {"phase": "DETECTED", "label": "Alert matched"}
event: phase        data: {"phase": "CORRELATING", "label": "Signals collected & compressed"}
event: meta         data: {"pattern": "OOMKill", "title": "Out-Of-Memory Kill", "context_meta": {...}}
event: facts        data: {"pattern": "OOMKill", "title": "...", "service": "payment-service", ..., "facts": [...]}
event: phase        data: {"phase": "ANALYZING", "label": "Generating analysis"}
event: token        data: {"t": "payment-service was OOMKilled: memory reached its limit 23 min after deploy v2.3.1..."}
event: token        data: {"t": "\n\nSuggested next checks:\n"}
event: token        data: {"t": "- Compare memory limit vs working set\n"}
... (more token frames) ...
event: phase        data: {"phase": "DONE", "label": "Report ready"}
event: done         data: {"report_markdown": "...", "elapsed_ms": 10, "total_ms": 10, "prep_ms": 7, "ttft_ms": ..., "llm": "deterministic"}
```

Order matches spec exactly: `phase(DETECTED)` → `phase(CORRELATING)` → `facts` (with `meta`
alongside/before it) → `phase(ANALYZING)` → `token`(s) → `phase(DONE)` → `done`.

## Alertmanager v4 webhook (`POST /v1/triage`)

Request (realistic Alertmanager v4 body, `KubePodOOMKilled` with pod-hash suffix):

```json
{
  "version": "4", "status": "firing", "receiver": "control-network",
  "commonLabels": {"alertname": "KubePodOOMKilled", "severity": "critical", "namespace": "prod", "cluster": "eks-prod-use1"},
  "alerts": [{
    "status": "firing",
    "labels": {"alertname": "KubePodOOMKilled", "namespace": "prod", "pod": "payment-service-7d9f8c6b5-x2k9p", "severity": "critical", "cluster": "eks-prod-use1"},
    "annotations": {"summary": "Pod payment-service-7d9f8c6b5-x2k9p was OOMKilled", "description": "Container exceeded memory limit"},
    "fingerprint": "abc123def456"
  }]
}
```

Response (200 OK):

```json
{
  "incident_id": "abc123def456",
  "pattern": "OOMKill",
  "report_markdown": "## Incident Report: abc123def456\n**Alert:** KubePodOOMKilled (Out-Of-Memory Kill) ...",
  "context_meta": {"tokens_before": 14, "tokens_after": 14, "truncated": false},
  "llm": "deterministic"
}
```

Confirms: `alert_id` taken from `fingerprint`, `service` derived from `pod` label with the
trailing ReplicaSet/pod hash stripped (`payment-service-7d9f8c6b5-x2k9p` → `payment-service`),
pattern matched from `alertname`, and no crash despite sim mode having no canned raw signals
for an ad-hoc alert (facts section correctly renders "no structured facts collected").

## Slack (`POST /api/slack`)

Request: `{"incident_id": "oom-payment-001"}` with `CN_SLACK_WEBHOOK_URL` unset.

Response (200 OK): `{"configured": false}` — confirms the UI's documented fallback path
(copy report to clipboard with an explanatory toast) is reachable and correctly triggered.

## Issues encountered and resolutions

- **Read/Write/Edit tools couldn't reach the mounted path** (`Control Network` cn/ directory)
  — they only see paths under the session's declared connected folders on the host side, while
  bash reaches a different mount (`/sessions/.../mnt/Control Network/cn`). Resolved by doing
  all file edits via `mcp__workspace__bash` heredocs instead of the Read/Edit/Write tools.
- **Background server processes did not survive across separate bash tool calls** — each
  `mcp__workspace__bash` invocation runs in its own network-namespaced sandbox
  (`bwrap --unshare-net --die-with-parent`), so a server backgrounded in one call is torn down
  when that call's shell exits. Resolved by starting the server, running all curl/verification
  steps, and stopping the server within a single bash call each time.
- No functional/code issues found — all pytest cases passed on the first full implementation
  pass; no test iteration was required beyond writing the new assertions.

## PASS/FAIL

- pytest green in `cn/`: **PASS** (6/6)
- pytest green in `Desktop/CN-MVP` copy: see below (verified after copy)
- Server boots and responds (`/healthz`, `/api/scenarios`, SSE stream, `/v1/triage`, `/api/slack`): **PASS**
- Desktop copy present and verified: see below
