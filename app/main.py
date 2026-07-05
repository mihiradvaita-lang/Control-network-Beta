# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""FastAPI app — locked HTTP contract on the Kimi-architected pipeline.

ZDR: incident data is request-scoped and in-RAM only — no DB, no disk writes, no logging of
incident/report content, so buffers are released by normal GC when the request ends. (There is
no explicit per-request scrub() call; see app/zdr.py for the optional in-place wipe helpers.)
"""
from __future__ import annotations
import logging
import re
import time
from typing import Any
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field as _Field, field_validator

from . import __version__, feedback
from .config import BASE_DIR, SKILLS_DIR, get_settings, load_skill_md
from .health import health
from .models import AlertPayload
from .pipeline import alert_from_scenario, prepare, stream_triage_events, triage_full
from .scenarios import list_scenarios, get_scenario
from .streamer import sse

app = FastAPI(title="Control Network — Triage Copilot", version=__version__)
_METRICS = {"triage_total": 0, "triage_errors": 0, "feedback_total": 0, "slack_posts": 0}


@app.middleware("http")
async def _security_headers(request, call_next):
    """Defense-in-depth for a local tool: no sniffing, no framing, no external resources.
    CSP allows only same-origin + inline (the UI is a single self-contained file)."""
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    # Isolate the browsing context and forbid cross-origin embedding of our resources.
    # These are same-origin only and do not affect same-origin fetch()/EventSource.
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    resp.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
    )
    return resp


_MAX_BODY_BYTES = 1_048_576  # 1 MiB — generous for triage/webhook JSON; blocks memory-DoS bodies


@app.middleware("http")
async def _require_token(request, call_next):
    """Optional Bearer-token guard for all write endpoints.
    Only enforced when CN_API_TOKEN is set; default (empty) disables auth so the app
    works out of the box and existing tests are unaffected."""
    settings = get_settings()
    if settings.api_token and request.method in ("POST", "PUT", "PATCH"):
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {settings.api_token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def _limit_body_size(request, call_next):
    """Reject oversized request bodies cheaply via Content-Length before FastAPI parses them.
    Only applies to body-bearing methods; GET/HEAD/OPTIONS and SSE streams are untouched, and
    static file serving (GET) is unaffected."""
    if request.method in ("POST", "PUT", "PATCH"):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > _MAX_BODY_BYTES:
                    return JSONResponse({"error": "request body too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"error": "invalid Content-Length"}, status_code=400)
    return await call_next(request)


logger = logging.getLogger("cn.main")


def _safe_err(e: Exception) -> str:
    """Sanitized 5xx error text. Never echo str(e): httpx and other libraries embed the
    request URL (which can be the secret Slack webhook URL) and other internal detail into
    exception messages. Deterministic 4xx validation errors keep their descriptive text;
    only unexpected 500s are reduced to the exception type name."""
    return type(e).__name__


def _run_llm_model_check() -> None:
    """One-shot reachability check for the configured Anthropic model so a bad model ID is
    logged loudly at startup instead of silently degrading every triage to deterministic."""
    settings = get_settings()
    if settings.llm_provider != "anthropic" or not settings.llm_enabled:
        return
    try:
        import httpx
        r = httpx.get(
            f"https://api.anthropic.com/v1/models/{settings.llm_model}",
            headers={"x-api-key": settings.anthropic_api_key,
                     "anthropic-version": "2023-06-01"},
            timeout=5.0,
        )
        r.raise_for_status()
    except httpx.TransportError:
        return  # no network at startup: don't cry wolf; per-request fallback still applies
    except Exception:
        logger.warning(
            "LLM model '%s' is unreachable — check CN_LLM_MODEL env var", settings.llm_model
        )


@app.on_event("startup")
def _verify_llm_model() -> None:
    """Fire the reachability probe on a daemon thread so its blocking (up to 5s) HTTP call
    never delays server readiness or first-request handling. The probe only logs a warning;
    nothing downstream waits on its result, so backgrounding it is safe."""
    import threading
    threading.Thread(target=_run_llm_model_check, name="llm-model-check", daemon=True).start()

_POD_HASH_SUFFIX = re.compile(r"-[0-9a-f]{6,10}-[0-9a-z]{5}$|-[0-9a-f]{8,12}$")


class FeedbackIn(BaseModel):
    # Length caps bound per-entry RAM in the fixed-size feedback ring buffer; vote is
    # constrained so callers cannot inject arbitrary strings into the buffer.
    incident_id: str = _Field(max_length=200)
    pattern: str = _Field(default="", max_length=200)
    vote: str = _Field(max_length=8)
    note: str = _Field(default="", max_length=1000)

    @field_validator("vote")
    @classmethod
    def _vote_in_range(cls, v: str) -> str:
        if v not in ("up", "down"):
            raise ValueError("vote must be 'up' or 'down'")
        return v


class SlackIn(BaseModel):
    incident_id: str | None = None
    scenario_id: str | None = None


@app.get("/api/scenarios")
def api_scenarios():
    return {"scenarios": list_scenarios(), "customer": get_settings().customer_name}


@app.post("/api/triage")
def api_triage(body: dict[str, Any]):
    scn = body.get("incident") or get_scenario(body.get("scenario_id", ""))
    if not scn:
        return JSONResponse({"error": "no incident or known scenario_id"}, status_code=400)
    if not isinstance(scn, dict):
        return JSONResponse({"error": "incident must be an object"}, status_code=400)
    try:
        out = triage_full(alert_from_scenario(dict(scn)))
        _METRICS["triage_total"] += 1
        return out
    except Exception as e:  # noqa
        _METRICS["triage_errors"] += 1
        return JSONResponse({"error": _safe_err(e)}, status_code=500)


@app.get("/api/triage/stream")
def api_triage_stream(scenario_id: str):
    scn = get_scenario(scenario_id)
    if not scn:
        return JSONResponse({"error": "unknown scenario_id"}, status_code=404)

    def gen():
        for frame in stream_triage_events(scn):
            yield frame
        _METRICS["triage_total"] += 1

    return StreamingResponse(gen(), media_type="text/event-stream")


def _strip_pod_hash(name: str) -> str:
    """Best-effort strip of a trailing ReplicaSet/Pod hash suffix, e.g.
    'payment-service-7d9f8c6b5-x2k9p' -> 'payment-service'. If it doesn't look like a
    hashed pod name, returns the input unchanged."""
    if not name:
        return name
    stripped = _POD_HASH_SUFFIX.sub("", name)
    return stripped or name


def _incident_from_alertmanager(payload: dict) -> dict | None:
    """Map a real Prometheus Alertmanager v4 webhook body to our internal incident shape.
    Robust to missing fields; falls back to commonLabels/commonAnnotations where useful."""
    alerts = payload.get("alerts") or []
    if not alerts:
        return None
    a0 = alerts[0]
    labels = a0.get("labels") or {}
    annotations = a0.get("annotations") or {}
    common_labels = payload.get("commonLabels") or {}
    common_annotations = payload.get("commonAnnotations") or {}

    alertname = labels.get("alertname") or common_labels.get("alertname") or ""
    service = (
        labels.get("service")
        or (_strip_pod_hash(labels["pod"]) if labels.get("pod") else None)
        or labels.get("deployment")
        or labels.get("app")
        or common_labels.get("service")
        or "unknown"
    )
    namespace = labels.get("namespace") or common_labels.get("namespace") or "default"
    cluster = labels.get("cluster") or common_labels.get("cluster") or "unknown"
    severity = labels.get("severity") or common_labels.get("severity") or "warning"
    summary = annotations.get("summary") or annotations.get("description") \
        or common_annotations.get("summary") or common_annotations.get("description") or ""

    fingerprint = a0.get("fingerprint")
    if fingerprint:
        alert_id = str(fingerprint)
    else:
        pod = labels.get("pod", "")
        alert_id = f"{alertname or 'ALERT'}-{pod}".strip("-") or "INC-live"

    raw = {"labels": labels, "annotations": annotations, "alerts_all_labels": [al.get("labels", {}) for al in alerts]}

    return {
        "id": alert_id, "alertname": alertname, "service": service,
        "namespace": namespace, "cluster": cluster, "severity": severity,
        "summary": summary, "raw": raw,
    }


@app.post("/v1/triage")
def v1_triage(payload: dict[str, Any]):
    incident = payload.get("incident")
    alerts = payload.get("alerts")
    if not incident and alerts:
        if not isinstance(alerts, list) or not isinstance(alerts[0], dict):
            return JSONResponse({"error": "alerts must be a list of objects"}, status_code=400)
        # Prefer the full Alertmanager v4 shape (labels/annotations/fingerprint/commonLabels).
        incident = _incident_from_alertmanager(payload)
        if not incident:
            # Legacy minimal shape: {"alerts":[{"labels": {...}, "raw": {...}}]}
            labels = payload["alerts"][0].get("labels", {})
            incident = {
                "id": labels.get("alertname", "INC") + "-live", "alertname": labels.get("alertname", ""),
                "service": labels.get("service") or labels.get("pod") or labels.get("deployment", "unknown"),
                "namespace": labels.get("namespace", "default"), "cluster": labels.get("cluster", "unknown"),
                "severity": labels.get("severity", "warning"), "raw": payload["alerts"][0].get("raw", {}),
            }
    if not incident:
        return JSONResponse({"error": "no alert/incident in payload"}, status_code=400)
    if not isinstance(incident, dict):
        return JSONResponse({"error": "incident must be an object"}, status_code=400)
    try:
        return triage_full(alert_from_scenario(dict(incident)))
    except Exception as e:  # noqa
        return JSONResponse({"error": _safe_err(e)}, status_code=500)


def _md_to_slack_text(md: str) -> str:
    """Very light markdown -> Slack mrkdwn conversion. Not exhaustive; good enough for a
    readable paste (bold conversion, header de-hashing)."""
    text = md
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", text, flags=re.MULTILINE)
    return text


@app.post("/api/slack")
def api_slack(body: SlackIn):
    scenario_id = body.scenario_id or body.incident_id
    scn = get_scenario(scenario_id) if scenario_id else None
    if not scn:
        return JSONResponse({"error": "unknown incident_id/scenario_id"}, status_code=404)

    settings = get_settings()
    if not settings.slack_webhook_url:
        return {"configured": False}

    try:
        out = triage_full(alert_from_scenario(dict(scn)))
    except Exception as e:  # noqa
        return JSONResponse({"error": _safe_err(e)}, status_code=500)

    text = _md_to_slack_text(out["report_markdown"])
    try:
        import httpx
        resp = httpx.post(settings.slack_webhook_url, json={"text": text}, timeout=5.0)
        _METRICS["slack_posts"] += 1
        return {"configured": True, "ok": resp.is_success, "status": resp.status_code}
    except Exception as e:  # noqa - never let a Slack failure look like a server crash
        return {"configured": True, "ok": False, "status": 0, "error": type(e).__name__}


@app.get("/api/specialized/template", response_class=PlainTextResponse)
def api_specialized_template():
    p = SKILLS_DIR / "specialized.template.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return PlainTextResponse("template not found", status_code=404)


@app.post("/api/feedback")
def api_feedback(body: FeedbackIn):
    _METRICS["feedback_total"] += 1
    return feedback.record(body.incident_id, body.pattern, body.vote, body.note)


@app.get("/healthz")
def healthz():
    return health()


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return "# Control Network metrics\n" + "".join(f"cn_{k} {v}\n" for k, v in _METRICS.items())


@app.get("/api/platforms")
def api_platforms():
    from .live import get_platform_status
    return get_platform_status()


@app.get("/api/incidents")
def api_incidents():
    """Returns live incidents from connected platforms, falling back to sim scenarios."""
    from .live import get_live_incidents, score_incident
    live = get_live_incidents()
    if live:
        for inc in live:
            inc["score"] = score_incident(inc)
        return {"incidents": live, "source": "live"}
    sims = sorted(list_scenarios(), key=score_incident, reverse=True)
    result = []
    for inc in sims:
        inc_copy = dict(inc)
        inc_copy["score"] = score_incident(inc)
        inc_copy.setdefault("platform", "sim")
        result.append(inc_copy)
    return {"incidents": result, "source": "sim"}


@app.get("/api/incidents/{incident_id}/stream")
def api_incident_stream(incident_id: str):
    """SSE triage stream for a single incident by ID (live or sim)."""
    from .live import get_live_incidents
    live = {i["id"]: i for i in get_live_incidents()}
    scn = live.get(incident_id) or get_scenario(incident_id)
    if not scn:
        return JSONResponse({"error": "unknown incident_id"}, status_code=404)

    def gen():
        for frame in stream_triage_events(scn):
            yield frame
        _METRICS["triage_total"] += 1

    return StreamingResponse(gen(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="static")
