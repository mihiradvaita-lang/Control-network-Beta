"""Audit iteration 3 — SECURITY regression tests. No network, no LLM; deterministic sim mode.

Covers: sanitized 5xx (no secret/URL leakage), /api/feedback input validation and RAM bounds,
request body-size guard (413), security headers on all responses (incl. SSE + static), loopback
binding config, and the /api/platforms credential-stripping. The frontend XSS defense is JS-only
(no JS runtime here) so it is verified at the API layer: malicious strings survive as inert data,
and the escaping contract is documented for manual verification below.
"""
import re
import pytest
from fastapi.testclient import TestClient
from app.main import app, _safe_err, _MAX_BODY_BYTES

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Sanitized 5xx: error responses must never echo a raw exception message
#    (httpx embeds the request URL — which can be the secret Slack webhook URL).
# ---------------------------------------------------------------------------

def test_safe_err_returns_type_name_only():
    class BoomError(Exception):
        pass
    e = BoomError("https://hooks.slack.com/services/T00/B00/SECRETTOKEN failed")
    out = _safe_err(e)
    assert out == "BoomError"
    assert "SECRETTOKEN" not in out
    assert "hooks.slack.com" not in out


def test_500_error_body_is_type_name_not_message(monkeypatch):
    # Force triage_full to raise with a secret-bearing message; response must not leak it.
    import app.main as m

    def boom(*a, **k):
        raise RuntimeError("connect to https://hooks.slack.com/services/SECRET failed")

    monkeypatch.setattr(m, "triage_full", boom)
    r = client.post("/api/triage", json={"scenario_id": "oom-payment-001"})
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "RuntimeError"
    assert "SECRET" not in r.text and "hooks.slack.com" not in r.text


# ---------------------------------------------------------------------------
# 2. /api/feedback input validation + RAM bounds (fixed-size ring buffer).
# ---------------------------------------------------------------------------

def test_feedback_rejects_bad_vote():
    r = client.post("/api/feedback", json={"incident_id": "i1", "vote": "maybe"})
    assert r.status_code == 422  # pydantic validation error


def test_feedback_accepts_up_down():
    for v in ("up", "down"):
        r = client.post("/api/feedback", json={"incident_id": "i1", "vote": v})
        assert r.status_code == 200
        assert r.json()["ok"] is True


def test_feedback_rejects_oversized_fields():
    # incident_id / pattern / note are length-capped to bound per-entry RAM growth.
    big = "x" * 5000
    assert client.post("/api/feedback",
                       json={"incident_id": big, "vote": "up"}).status_code == 422
    assert client.post("/api/feedback",
                       json={"incident_id": "i", "pattern": big, "vote": "up"}).status_code == 422
    assert client.post("/api/feedback",
                       json={"incident_id": "i", "vote": "up", "note": big}).status_code == 422


# ---------------------------------------------------------------------------
# 3. Request body-size guard: oversized Content-Length -> 413 before parsing.
# ---------------------------------------------------------------------------

def test_oversized_body_rejected_413():
    huge = _MAX_BODY_BYTES + 1
    r = client.post("/v1/triage", content=b"x",
                    headers={"content-length": str(huge), "content-type": "application/json"})
    assert r.status_code == 413


def test_invalid_content_length_rejected_400():
    r = client.post("/v1/triage", content=b"{}",
                    headers={"content-length": "not-a-number", "content-type": "application/json"})
    assert r.status_code == 400


def test_normal_sized_body_passes():
    r = client.post("/api/triage", json={"scenario_id": "oom-payment-001"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 4. Security headers present on every response type: JSON, static, SSE.
# ---------------------------------------------------------------------------

_EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "x-permitted-cross-domain-policies": "none",
}


def _assert_headers(resp):
    for k, v in _EXPECTED_HEADERS.items():
        assert resp.headers.get(k) == v, f"missing/incorrect {k}"
    assert "content-security-policy" in resp.headers


def test_headers_on_json_endpoint():
    _assert_headers(client.get("/healthz"))


def test_headers_on_static_index():
    _assert_headers(client.get("/"))


def test_headers_on_sse_stream():
    # SSE responses must also carry the security headers.
    r = client.get("/api/triage/stream", params={"scenario_id": "oom-payment-001"})
    assert r.status_code == 200
    _assert_headers(r)


# ---------------------------------------------------------------------------
# 5. Loopback binding: config default must be 127.0.0.1.
# ---------------------------------------------------------------------------

def test_default_host_is_loopback():
    from app.config import Settings
    assert Settings().host == "127.0.0.1"


# ---------------------------------------------------------------------------
# 6. /api/platforms must strip embedded userinfo credentials from prometheus_url.
# ---------------------------------------------------------------------------

def test_sanitize_url_strips_credentials():
    from app.live import _sanitize_url
    out = _sanitize_url("https://user:s3cret@prom.example.com:9090/path")
    assert "s3cret" not in out and "user" not in out
    assert "prom.example.com:9090" in out


def test_sanitize_url_passthrough_when_no_creds():
    from app.live import _sanitize_url
    assert _sanitize_url("http://alertmanager:9093") == "http://alertmanager:9093"
    assert _sanitize_url("") == ""


# ---------------------------------------------------------------------------
# 7. XSS: attacker-influenced fields (alertname/service/summary from webhooks)
#    survive the API round-trip as INERT DATA (never executed/transformed server
#    side). Client-side rendering escapes them via escapeHtml()/renderMd()'s esc.
#    See MANUAL VERIFICATION below for the JS-only escaping contract.
# ---------------------------------------------------------------------------

_XSS = "<img src=x onerror=alert(1)>"


def test_malicious_webhook_fields_survive_as_data():
    r = client.post("/v1/triage", json={
        "alerts": [{"labels": {"alertname": _XSS, "service": _XSS, "namespace": "default"},
                    "annotations": {"summary": _XSS}}],
    })
    assert r.status_code == 200
    # The payload is treated as data; it may appear in the report body verbatim (the frontend
    # is responsible for escaping at the render boundary). Assert the server did not, e.g.,
    # execute or reflect it into a header.
    for hv in r.headers.values():
        assert "onerror=alert" not in hv


def test_no_user_input_reflected_into_response_headers():
    # Header-injection guard: nothing user-controlled reaches response headers.
    r = client.post("/api/triage", json={"incident": {
        "id": "x", "alertname": "A\r\nX-Injected: yes", "service": "s",
        "namespace": "default", "cluster": "c", "severity": "warning", "summary": "s",
    }})
    assert "x-injected" not in {k.lower() for k in r.headers}


# MANUAL VERIFICATION (frontend escaping, no JS runtime in this suite):
#   1. escapeHtml() escapes & < > " — used for every incident field (service, alertname,
#      summary, namespace, cluster, id) in cardHtml/renderPanelHead/renderStructured/renderEvidence.
#   2. renderMd()'s inner esc() escapes & < > BEFORE applying **/* markdown transforms, and
#      renderMd has NO link/image/href transforms, so no attribute-context injection is possible.
#   To manually confirm: send a webhook with alertname="<img src=x onerror=alert(1)>", open the
#   UI, and verify the string renders as visible text (escaped) with no alert() firing.
