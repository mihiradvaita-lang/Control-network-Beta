"""Audit iteration 1 regression tests — malformed-input validation holes and the
frontend priority-report regex. No network, no LLM, deterministic sim mode.
"""
import re
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# --- Bug 1/2: malformed bodies must be rejected with 4xx, never crash to 500 ---

def test_api_triage_non_dict_incident_returns_400():
    # dict("x") / dict([1,2]) used to raise inside the handler -> 500. Now 400.
    assert client.post("/api/triage", json={"incident": "x"}).status_code == 400
    assert client.post("/api/triage", json={"incident": [1, 2]}).status_code == 400


def test_v1_triage_bad_alerts_shape_returns_400():
    # alerts[0] not a dict used to raise AttributeError *outside* the try -> uncaught 500.
    assert client.post("/v1/triage", json={"alerts": ["x"]}).status_code == 400
    assert client.post("/v1/triage", json={"alerts": "x"}).status_code == 400
    assert client.post("/v1/triage", json={"incident": "x"}).status_code == 400


def test_valid_paths_still_work():
    # Guard against over-eager validation breaking the happy path.
    assert client.post("/api/triage", json={"scenario_id": "oom-payment-001"}).status_code == 200
    r = client.post(
        "/v1/triage",
        json={"alerts": [{"labels": {"alertname": "KubePodOOMKilled", "service": "p"}}]},
    )
    assert r.status_code == 200


# --- Bug 3: priority-report section extraction must not truncate multi-line bodies ---
# Mirror of parsePriorityReport()'s per-section regex in app/static/index.html.

def _extract(text: str, header: str):
    # Python equivalent of the corrected JS regex:
    #   /\*\*HEADER\*\*\s*([\s\S]*?)(?=\n\*\*[A-Z]|\n---|$)/i
    pat = re.compile(r"\*\*" + header + r"\*\*\s*(.*?)(?=\n\*\*[A-Z]|\n---|$)",
                     re.IGNORECASE | re.DOTALL)
    m = pat.search(text)
    return m.group(1).strip() if m else None


REPORT = (
    "**PRIORITY: CRITICAL**\n\n"
    "**WHAT HAPPENED**\n"
    "payment-service was OOMKilled after memory spiked.\n"
    "Impact: 500 errors on checkout.\n\n"
    "**ROOT CAUSE**\n"
    "Memory leak after deploy v2.3.1.\n\n"
    "**WATCH FOR**\n"
    "- memory usage\n"
    "- error rate\n\n"
    "---\n"
    "*Advisory only.*\n"
)


def test_multiline_section_not_truncated_to_first_line():
    what = _extract(REPORT, "WHAT HAPPENED")
    assert "Impact: 500 errors on checkout." in what
    assert "payment-service was OOMKilled" in what


def test_section_stops_at_next_header_and_hr():
    root = _extract(REPORT, "ROOT CAUSE")
    assert root == "Memory leak after deploy v2.3.1."
    watch = _extract(REPORT, "WATCH FOR")
    assert "- memory usage" in watch and "- error rate" in watch
    assert "Advisory only" not in watch
