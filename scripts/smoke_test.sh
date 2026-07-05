#!/usr/bin/env bash
# Control Network smoke test — validates the full alert → triage → Slack pipeline.
# Supports DRY_RUN mode: when SLACK_WEBHOOK_URL is unset (or DRY_RUN=1), prints the
# would-be Slack message to stdout instead of posting, so the whole pipeline can be
# verified before connecting real Slack.
#
# Usage:
#   ./scripts/smoke_test.sh                     # against localhost:8000
#   CN_BASE_URL=http://myhost:8000 ./scripts/smoke_test.sh
#   DRY_RUN=1 ./scripts/smoke_test.sh
#
# Environment:
#   CN_BASE_URL   — server to test (default: http://localhost:8000)
#   CN_API_TOKEN  — Bearer token (required when server has CN_API_TOKEN set)
#   DRY_RUN       — set to "1" to force dry-run (also auto-activates when SLACK_WEBHOOK_URL unset)
set -euo pipefail

BASE_URL="${CN_BASE_URL:-http://localhost:8000}"
TOKEN="${CN_API_TOKEN:-}"
DRY_RUN="${DRY_RUN:-0}"
SLACK_URL="${CN_SLACK_WEBHOOK_URL:-${SLACK_WEBHOOK_URL:-}}"

GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; RESET="\033[0m"
pass() { printf "${GREEN}PASS${RESET}  %s\n" "$*"; }
warn() { printf "${YELLOW}WARN${RESET}  %s\n" "$*"; }
fail() { printf "${RED}FAIL${RESET}  %s\n" "$*"; exit 1; }

echo ""
echo "=== Control Network Smoke Test ==="
echo "  Server : $BASE_URL"
echo "  Token  : ${TOKEN:+(set)}${TOKEN:-  (unset — auth disabled)}"
echo ""

# ── 1. Health check ──────────────────────────────────────────────────────────
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/healthz")
[ "$STATUS" = "200" ] && pass "/healthz returned 200" || fail "/healthz returned $STATUS (is the server running?)"

PROVIDER=$(curl -sf "$BASE_URL/healthz" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('llm_provider','?'))")
echo "       LLM provider: $PROVIDER"

# ── 2. Auth rejection (only tested when CN_API_TOKEN is configured) ──────────
if [ -n "$TOKEN" ]; then
    NO_AUTH=$(curl -s -o /dev/null -w "%{http_code}" \
              -X POST "$BASE_URL/v1/triage" \
              -H "Content-Type: application/json" \
              -d '{"alerts":[{"labels":{"alertname":"test"}}]}')
    [ "$NO_AUTH" = "401" ] && pass "auth rejection: POST without token → 401" \
                           || fail "expected 401 without token, got $NO_AUTH"
fi

# ── 3. Alert ingestion via Alertmanager v4 payload ───────────────────────────
PAYLOAD='{
  "version": "4",
  "status": "firing",
  "receiver": "control-network",
  "commonLabels": {"alertname": "KubePodOOMKilled", "severity": "critical",
                   "namespace": "prod", "cluster": "eks-prod-use1"},
  "alerts": [{
    "status": "firing",
    "labels": {"alertname": "KubePodOOMKilled", "namespace": "prod",
                "pod": "payment-svc-7d9f8c6b5-x2k9p", "severity": "critical",
                "cluster": "eks-prod-use1"},
    "annotations": {"summary": "Pod payment-svc was OOMKilled by container runtime"},
    "fingerprint": "smoketest-oom-001"
  }]
}'

if [ -n "$TOKEN" ]; then
    RESP=$(curl -sf -X POST "$BASE_URL/v1/triage" \
           -H "Content-Type: application/json" \
           -H "Authorization: Bearer $TOKEN" \
           -d "$PAYLOAD")
else
    RESP=$(curl -sf -X POST "$BASE_URL/v1/triage" \
           -H "Content-Type: application/json" \
           -d "$PAYLOAD")
fi

PATTERN=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('pattern','?'))" 2>/dev/null || echo "?")
REPORT=$(echo "$RESP"  | python3 -c "import sys,json; print(json.load(sys.stdin).get('report_markdown',''))" 2>/dev/null || echo "")

[ -n "$REPORT" ] && pass "alert ingestion → pattern: $PATTERN" \
                 || fail "alert ingestion: empty or malformed response"

# ── 4. Metrics endpoint ───────────────────────────────────────────────────────
METRICS=$(curl -sf "$BASE_URL/metrics")
echo "$METRICS" | grep -q "cn_triage_total" && pass "/metrics returns triage counter" \
                                             || warn "/metrics missing cn_triage_total"

# ── 5. Slack / DRY_RUN ───────────────────────────────────────────────────────
if [ -z "$SLACK_URL" ] || [ "$DRY_RUN" = "1" ]; then
    echo ""
    printf "${YELLOW}DRY RUN${RESET} — SLACK_WEBHOOK_URL not set; printing would-be Slack message:\n"
    echo "────────────────────────────────────────────────────────────────────"
    echo "$REPORT"
    echo "────────────────────────────────────────────────────────────────────"
    pass "dry-run pipeline complete (full report generated without network)"
else
    pass "Slack webhook configured — post via UI (press 's') or POST /api/slack"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== All checks passed ==="
echo "   Open http://localhost:8000 to use the UI"
echo "   Run 'python -m pytest tests/ -v' for the full test suite"
echo ""
