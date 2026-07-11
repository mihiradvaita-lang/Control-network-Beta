"""API-token (Bearer) write-guard tests.

Verifies the optional CN_API_TOKEN enforcement in app.main._require_token:
- when a token is set, POST/PUT/PATCH require the correct Bearer token (401 otherwise);
- GET endpoints (including the SSE stream) are never affected;
- when no token is set (default), write endpoints work with no Authorization header,
  so the same-origin UI (which sends none) keeps working.

Deterministic sim mode; no network, no LLM.
"""
import pytest
from fastapi.testclient import TestClient

import app.config as config
import app.main as main


@pytest.fixture
def token_client(monkeypatch):
    """Build a TestClient with CN_API_TOKEN enforced."""
    monkeypatch.setenv("CN_API_TOKEN", "secret123")
    config.get_settings.cache_clear()
    client = TestClient(main.app)
    yield client
    config.get_settings.cache_clear()


@pytest.fixture
def no_token_client(monkeypatch):
    """Build a TestClient with no CN_API_TOKEN (default, auth disabled)."""
    monkeypatch.delenv("CN_API_TOKEN", raising=False)
    config.get_settings.cache_clear()
    client = TestClient(main.app)
    yield client
    config.get_settings.cache_clear()


_FEEDBACK = {"incident_id": "i1", "pattern": "", "vote": "up", "note": ""}


# --- token set: writes require the right Bearer ---------------------------

def test_write_rejected_without_token(token_client):
    r = token_client.post("/api/feedback", json=_FEEDBACK)
    assert r.status_code == 401


def test_write_rejected_with_wrong_token(token_client):
    r = token_client.post(
        "/api/feedback", json=_FEEDBACK,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_write_accepted_with_right_token(token_client):
    r = token_client.post(
        "/api/feedback", json=_FEEDBACK,
        headers={"Authorization": "Bearer secret123"},
    )
    assert r.status_code == 200


# --- token set: GET endpoints are unaffected ------------------------------

def test_get_unaffected_by_token(token_client):
    assert token_client.get("/api/scenarios").status_code == 200
    assert token_client.get("/healthz").status_code == 200


def test_sse_stream_get_unaffected_by_token(token_client):
    # GET SSE stream must not require a token even when one is set.
    r = token_client.get("/api/triage/stream", params={"scenario_id": "oom-payment-001"})
    assert r.status_code == 200


# --- token unset (default): UI keeps working, no header needed -------------

def test_write_works_without_token_when_unset(no_token_client):
    r = no_token_client.post("/api/feedback", json=_FEEDBACK)
    assert r.status_code == 200
