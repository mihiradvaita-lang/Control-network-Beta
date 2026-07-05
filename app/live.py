# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Live incident fetcher — pulls real active alerts from Prometheus Alertmanager and Datadog
in parallel. All network calls are best-effort and wrapped in try/except so a platform outage
never crashes the pipeline; callers fall back to sim scenarios when this returns [].
"""
from __future__ import annotations
import concurrent.futures
from typing import Any

from .config import get_settings


# ---------- priority scoring ----------

def score_incident(inc: dict) -> int:
    sev = (inc.get("severity") or "info").lower()
    score = {"critical": 100, "high": 80, "warning": 50, "info": 20}.get(sev, 20)
    name = (inc.get("alertname") or "").lower()
    if "crashloop" in name:
        score += 30
    if "oomkill" in name or "oom" in name:
        score += 20
    if "diskpressure" in name or "disk" in name:
        score += 15
    if "latency" in name or "highlatency" in name:
        score += 10
    if "config" in name or "configerror" in name:
        score += 5
    if inc.get("live"):
        score += 10
    return score


# ---------- Prometheus Alertmanager ----------

def _fetch_prometheus() -> list[dict]:
    s = get_settings()
    if not s.prometheus_enabled:
        return []
    import httpx
    url = s.prometheus_url.rstrip("/") + "/api/v2/alerts"
    headers = {"Authorization": f"Bearer {s.prometheus_token}"} if s.prometheus_token else {}
    try:
        r = httpx.get(url, params={"active": "true", "silenced": "false"},
                      headers=headers, timeout=4.0)
        r.raise_for_status()
        alerts = r.json()
    except Exception:
        return []

    out: list[dict] = []
    for alert in alerts:
        labels: dict[str, Any] = alert.get("labels") or {}
        annotations: dict[str, Any] = alert.get("annotations") or {}
        inc: dict[str, Any] = {
            "id": f"prom-{labels.get('alertname', 'alert')}-{labels.get('pod', '')}-live",
            "alertname": labels.get("alertname", ""),
            "service": (labels.get("service")
                        or labels.get("pod")
                        or labels.get("deployment", "unknown")),
            "namespace": labels.get("namespace", "default"),
            "cluster": labels.get("cluster", "unknown"),
            "severity": labels.get("severity", "warning"),
            "summary": (annotations.get("summary", "")
                        or annotations.get("description", "")),
            "platform": "prometheus",
            "raw": {"metrics": {}, "logs": [], "events": []},
            "live": True,
        }
        out.append(inc)
    return out


# ---------- Datadog ----------

def _fetch_datadog() -> list[dict]:
    s = get_settings()
    if not s.datadog_enabled:
        return []
    import httpx
    url = f"https://api.{s.datadog_site}/api/v1/monitor/triggered_monitors"
    headers = {
        "DD-API-KEY": s.datadog_api_key,
        "DD-APPLICATION-KEY": s.datadog_app_key,
    }
    try:
        r = httpx.get(url, headers=headers, timeout=4.0)
        r.raise_for_status()
        monitors = r.json()
    except Exception:
        return []

    out: list[dict] = []
    for m in (monitors or []):
        tags: list[str] = m.get("tags") or []
        service = (
            next((t.replace("service:", "") for t in tags if t.startswith("service:")), None)
            or m.get("name", "unknown")[:30]
        )
        namespace = next(
            (t.replace("namespace:", "") for t in tags if t.startswith("namespace:")), "default"
        )
        cluster = next(
            (t.replace("cluster:", "") for t in tags if t.startswith("cluster:")), "unknown"
        )
        overall_state = (m.get("overall_state") or "").lower()
        severity = "critical" if overall_state in ("alert", "no data") else "warning"
        inc: dict[str, Any] = {
            "id": f"dd-{m.get('id', '')}-live",
            "alertname": m.get("name", ""),
            "service": service,
            "namespace": namespace,
            "cluster": cluster,
            "severity": severity,
            "summary": m.get("name", ""),
            "platform": "datadog",
            "raw": {"metrics": {}, "logs": [], "events": []},
            "live": True,
        }
        out.append(inc)
    return out


# ---------- main entry points ----------

def get_live_incidents(timeout: float = 4.0) -> list[dict]:
    """Fetch active alerts from all configured platforms in parallel.
    Returns [] when no platforms are configured (caller should use sim fallback).
    Never raises."""
    s = get_settings()
    fetchers = []
    if s.prometheus_enabled:
        fetchers.append(_fetch_prometheus)
    if s.datadog_enabled:
        fetchers.append(_fetch_datadog)
    if not fetchers:
        return []

    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(fetchers)) as pool:
        futures = [pool.submit(fn) for fn in fetchers]
        for fut in concurrent.futures.as_completed(futures, timeout=timeout + 1):
            try:
                results.extend(fut.result())
            except Exception:
                pass

    # deduplicate by id, sort by priority descending
    seen: set[str] = set()
    unique: list[dict] = []
    for inc in results:
        if inc["id"] not in seen:
            seen.add(inc["id"])
            unique.append(inc)
    return sorted(unique, key=score_incident, reverse=True)


import time as _time

# Probe cache: /api/platforms is polled by the UI; without a TTL every poll would pay up to
# 2x2s of network probing (and block the header render when a platform is down).
_PROBE_CACHE: dict[str, tuple[float, bool]] = {}
_PROBE_TTL_S = 15.0


def _cached(key: str, fn) -> bool:
    now = _time.monotonic()
    hit = _PROBE_CACHE.get(key)
    if hit and now - hit[0] < _PROBE_TTL_S:
        return hit[1]
    val = bool(fn())
    _PROBE_CACHE[key] = (now, val)
    return val


def _probe_prometheus() -> bool:
    """Cheap reachability check against Alertmanager. Best-effort, 2s cap."""
    s = get_settings()
    if not s.prometheus_enabled:
        return False
    try:
        import httpx
        r = httpx.get(s.prometheus_url.rstrip("/") + "/api/v2/status", timeout=2.0)
        return r.status_code < 500
    except Exception:
        return False


def _probe_datadog() -> bool:
    s = get_settings()
    if not s.datadog_enabled:
        return False
    try:
        import httpx
        r = httpx.get(
            f"https://api.{s.datadog_site}/api/v1/validate",
            headers={"DD-API-KEY": s.datadog_api_key}, timeout=2.0,
        )
        return r.status_code == 200
    except Exception:
        return False


def _sanitize_url(url: str) -> str:
    """Strip any embedded userinfo (user:pass@) from a URL before exposing it to the client.
    prometheus_url is operator-controlled, but some deployments embed basic-auth credentials
    directly in the URL; those must never be echoed by /api/platforms."""
    if not url:
        return url
    try:
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(url)
        if parts.username or parts.password:
            netloc = parts.hostname or ""
            if parts.port:
                netloc = f"{netloc}:{parts.port}"
            parts = parts._replace(netloc=netloc)
        return urlunsplit(parts)
    except Exception:
        return url


def get_platform_status() -> dict:
    s = get_settings()
    prom_configured = s.prometheus_enabled
    dd_configured = s.datadog_enabled
    prom_reachable = _cached("prom", _probe_prometheus) if prom_configured else False
    dd_reachable = _cached("dd", _probe_datadog) if dd_configured else False
    return {
        "prometheus": {
            "configured": prom_configured,
            "reachable": prom_reachable,
            "url": _sanitize_url(s.prometheus_url) if prom_configured else None,
        },
        "datadog": {
            "configured": dd_configured,
            "reachable": dd_reachable,
            "site": s.datadog_site if dd_configured else None,
        },
        "any_live": prom_configured or dd_configured,
        "any_reachable": prom_reachable or dd_reachable,
    }
