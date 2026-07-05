# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Real data connectors — Prometheus + Datadog + Kubernetes + GitHub. Designed by Kimi
(see research/kimi-connectors.md), implemented by Claude. BEST-EFFORT: any error/timeout
returns None so the caller falls back to sim. Latency is sacred — short timeouts, never
raise into the pipeline. Read-only API verbs only; guarded imports so sim mode needs no
heavy deps.
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx

from .config import get_settings
from .models import AlertPayload, Signal, SignalSource
from .patterns import match_pattern


# ---------- pure parsers (unit-tested, no network) ----------
def parse_prom_scalar(payload: dict) -> float | None:
    """Extract the first value from a Prometheus /api/v1/query vector|scalar response."""
    try:
        data = payload.get("data", {})
        rt = data.get("resultType")
        if rt == "scalar":
            return float(data["result"][1])
        res = data.get("result", [])
        if res:
            return float(res[0]["value"][1])
    except Exception:
        return None
    return None


def parse_dd_series_last(payload: dict) -> float | None:
    """Last point value from a Datadog /api/v1/query timeseries response."""
    try:
        series = payload.get("series", [])
        if series and series[0].get("pointlist"):
            return float(series[0]["pointlist"][-1][1])
    except Exception:
        return None
    return None


def parse_dd_logs(payload: dict, limit: int = 8) -> list[str]:
    """Message lines from a Datadog /api/v2/logs/events/search response."""
    out: list[str] = []
    try:
        for ev in payload.get("data", [])[:limit]:
            msg = (ev.get("attributes", {}) or {}).get("message")
            if msg:
                out.append(str(msg)[:300])
    except Exception:
        return out
    return out


# ---------- Prometheus ----------
def _prom_query(promql: str) -> float | None:
    s = get_settings()
    url = s.prometheus_url.rstrip("/") + "/api/v1/query"
    headers = {"Authorization": f"Bearer {s.prometheus_token}"} if s.prometheus_token else {}
    try:
        r = httpx.get(url, params={"query": promql}, headers=headers, timeout=s.prometheus_timeout)
        r.raise_for_status()
        return parse_prom_scalar(r.json())
    except Exception:
        return None


def _scope(alert: AlertPayload) -> str:
    ns = alert.namespace or "default"
    svc = alert.service or ".*"
    return f'namespace="{ns}",pod=~"{svc}.*"'


def prometheus_collect(name: str, alert: AlertPayload) -> Signal | None:
    """Returns a metric Signal for metric-type collectors; None (=> sim fallback) otherwise."""
    pid, _, _ = match_pattern(alert.alertname)
    sc = _scope(alert)
    facts: dict[str, Any] = {}
    if name == "metrics" and pid == "OOMKill":
        used = _prom_query(f"max(container_memory_working_set_bytes{{{sc}}})")
        lim = _prom_query(f'max(kube_pod_container_resource_limits{{resource="memory",{sc}}})')
        if used is not None:
            facts["memory_working_set_bytes"] = int(used)
        if lim:
            facts["memory_limit_bytes"] = int(lim)
            if used is not None:
                facts["memory_pct"] = round(used / lim * 100, 1)
    elif name == "metrics" and pid == "HighLatency":
        p99 = _prom_query(
            f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{service="{alert.service}"}}[5m])) by (le))')
        if p99 is not None:
            facts["p99_latency_s"] = round(p99, 3)
    elif name == "saturation":
        cpu = _prom_query(
            f"sum(rate(container_cpu_usage_seconds_total{{{sc}}}[5m])) "
            f'/ sum(kube_pod_container_resource_limits{{resource="cpu",{sc}}})')
        if cpu is not None:
            facts["cpu_saturation"] = round(cpu, 3)
    elif name == "disk":
        ns = alert.namespace or "default"
        used = _prom_query(f'max(kubelet_volume_stats_used_bytes{{namespace="{ns}"}})')
        cap = _prom_query(f'max(kubelet_volume_stats_capacity_bytes{{namespace="{ns}"}})')
        if used is not None and cap:
            facts["volume_used_pct"] = round(used / cap * 100, 1)
    if not facts:
        return None
    return Signal(kind="metric", source=SignalSource(collector=name, provenance="high"), data=facts)


# ---------- Kubernetes ----------
# Lazy-cached API clients. NOTE: cache vars are separate names from the functions
# (Kimi's draft shadowed the function name with a module global, which broke the
# collector permanently after the first call — fixed here).
_K8S_V1: Any = None
_K8S_APPS_V1: Any = None


def _k8s_load_config() -> bool:
    """Load kubeconfig or in-cluster config. Returns False on any failure."""
    try:
        from kubernetes import config as k8s_config
    except ImportError:
        return False
    s = get_settings()
    if not s.k8s_enabled:
        return False
    try:
        if s.kubeconfig:
            k8s_config.load_kube_config(config_file=s.kubeconfig)
        else:
            k8s_config.load_incluster_config()
        return True
    except Exception:
        return False


def _k8s_v1() -> Any:
    """Lazy-init CoreV1Api; None if the kubernetes client is unavailable/unconfigured."""
    global _K8S_V1
    if _K8S_V1 is not None:
        return _K8S_V1
    if not _k8s_load_config():
        return None
    try:
        from kubernetes import client
        _K8S_V1 = client.CoreV1Api()
        return _K8S_V1
    except Exception:
        return None


def _k8s_apps_v1() -> Any:
    """Lazy-init AppsV1Api; None if the kubernetes client is unavailable/unconfigured."""
    global _K8S_APPS_V1
    if _K8S_APPS_V1 is not None:
        return _K8S_APPS_V1
    if not _k8s_load_config():
        return None
    try:
        from kubernetes import client
        _K8S_APPS_V1 = client.AppsV1Api()
        return _K8S_APPS_V1
    except Exception:
        return None


def _k8s_pod_name(service: str, namespace: str) -> str | None:
    """First pod matching app=<service>; None on any failure."""
    v1 = _k8s_v1()
    if v1 is None or not service:
        return None
    try:
        t = get_settings().k8s_timeout
        pods = v1.list_namespaced_pod(namespace, label_selector=f"app={service}",
                                      timeout_seconds=int(t), _request_timeout=t)
        for pod in pods.items:
            if pod.metadata and pod.metadata.name:
                return pod.metadata.name
        return None
    except Exception:
        return None


def k8s_collect(name: str, alert: AlertPayload) -> Signal | None:
    """Best-effort Kubernetes collector. Returns Signal on success, None on any failure
    (=> sim fallback). Read-only API verbs only. Each branch fetches the API client it
    needs, so an AppsV1-only call still works if CoreV1 init failed and vice versa."""
    t = get_settings().k8s_timeout
    service = alert.service or ""
    namespace = alert.namespace or "default"

    if name == "pod_describe":
        v1 = _k8s_v1()
        if v1 is None:
            return None
        pod_name = _k8s_pod_name(service, namespace)
        if pod_name is None:
            return None
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace, _request_timeout=t)
            status = pod.status
            container_statuses = (status.container_statuses if status else None) or []
            last_state = None
            oom_killed = False
            restart_count = 0
            exit_code = None
            for cs in container_statuses:
                if cs.last_state and cs.last_state.terminated:
                    term = cs.last_state.terminated
                    last_state = term.reason or "Unknown"
                    oom_killed = term.reason == "OOMKilled"
                    exit_code = term.exit_code
                restart_count = max(restart_count, cs.restart_count or 0)
            return Signal(
                kind="describe",
                source=SignalSource(collector=name, provenance="high"),
                data={
                    "phase": (status.phase if status else None) or "Unknown",
                    "last_state_reason": last_state,
                    "restart_count": restart_count,
                    "oom_killed": oom_killed,
                    "exit_code": exit_code,
                },
            )
        except Exception:
            return None

    if name == "events":
        v1 = _k8s_v1()
        if v1 is None:
            return None
        try:
            events = v1.list_namespaced_event(
                namespace,
                field_selector=f"involvedObject.name={service}",
                _request_timeout=t,
            )
            items: list[str] = []
            for ev in events.items:
                age = ev.last_timestamp.strftime("%Y-%m-%d %H:%M") if ev.last_timestamp else "unknown"
                items.append(f"{age} {ev.type or 'Unknown'} {ev.reason or 'Unknown'} {ev.message or ''}")
                if len(items) >= 10:
                    break
            if not items:
                return None
            return Signal(
                kind="event",
                source=SignalSource(collector=name, provenance="high"),
                data={"items": items},
            )
        except Exception:
            return None

    if name == "logs":
        v1 = _k8s_v1()
        if v1 is None:
            return None
        pod_name = _k8s_pod_name(service, namespace)
        if pod_name is None:
            return None
        lines: list[str] = []
        try:
            log = v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=50,
                                             previous=False, _request_timeout=t)
            if log:
                lines = log.strip().split("\n")
        except Exception:
            pass
        if not lines:
            try:
                log = v1.read_namespaced_pod_log(pod_name, namespace, tail_lines=50,
                                                 previous=True, _request_timeout=t)
                if log:
                    lines = log.strip().split("\n")
            except Exception:
                pass
        if not lines:
            return None  # let sim provide log lines rather than shipping an empty signal
        return Signal(
            kind="log",
            source=SignalSource(collector=name, provenance="medium"),
            data={"lines": lines},
        )

    if name == "deployment":
        apps = _k8s_apps_v1()
        if apps is None or not service:
            return None
        try:
            dep = apps.read_namespaced_deployment(service, namespace, _request_timeout=t)
            return Signal(
                kind="deploy",
                source=SignalSource(collector=name, provenance="high"),
                data={
                    "replicas": dep.spec.replicas if dep.spec else None,
                    "available_replicas": dep.status.available_replicas if dep.status else None,
                },
            )
        except Exception:
            return None

    if name == "node_describe":
        v1 = _k8s_v1()
        if v1 is None:
            return None
        pod_name = _k8s_pod_name(service, namespace)
        if pod_name is None:
            return None
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace, _request_timeout=t)
            node_name = pod.spec.node_name if pod.spec else None
            if not node_name:
                return None
            node = v1.read_node(node_name, _request_timeout=t)
            conditions = {c.type: c.status for c in (node.status.conditions or [])}
            bad = next((k for k, v in conditions.items()
                        if k != "Ready" and v == "True"), None)
            if conditions.get("Ready") != "True":
                bad = bad or "NotReady"
            return Signal(
                kind="describe",
                source=SignalSource(collector=name, provenance="high"),
                data={"node": node_name, "condition": bad or "Ready"},
            )
        except Exception:
            return None

    if name == "pvc":
        v1 = _k8s_v1()
        if v1 is None:
            return None
        try:
            pvcs = v1.list_namespaced_persistent_volume_claim(
                namespace, label_selector=f"app={service}", _request_timeout=t)
            if not pvcs.items:
                return None
            pvc = pvcs.items[0]
            status = pvc.status
            return Signal(
                kind="describe",
                source=SignalSource(collector=name, provenance="medium"),
                data={
                    "name": pvc.metadata.name if pvc.metadata else None,
                    "capacity": status.capacity.get("storage") if status and status.capacity else None,
                    "status": status.phase if status else None,
                },
            )
        except Exception:
            return None

    return None


# ---------- GitHub ----------
def _github_client() -> httpx.Client | None:
    s = get_settings()
    if not s.github_enabled:
        return None
    return httpx.Client(
        headers={
            "Authorization": f"token {s.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=s.github_timeout,
    )


def _parse_pr(pr: dict[str, Any]) -> str:
    number = pr.get("number", "?")
    title = pr.get("title", "untitled")
    author = (pr.get("user") or {}).get("login", "unknown")
    merged_at = pr.get("merged_at")
    age_str = "recently"
    if merged_at:
        try:
            dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - dt
            if age < timedelta(hours=1):
                age_str = f"{int(age.total_seconds() // 60)}m ago"
            elif age < timedelta(days=1):
                age_str = f"{int(age.total_seconds() // 3600)}h ago"
            else:
                age_str = f"{age.days}d ago"
        except Exception:
            age_str = "recently"
    return f"#{number} {title} ({author}, {age_str})"


def github_collect(name: str, alert: AlertPayload) -> Signal | None:
    """Best-effort GitHub collector (merged PRs in the last 24h). Returns Signal on
    success, None on any failure (=> sim fallback). Read-only REST calls only."""
    if name != "recent_changes":
        return None
    client = _github_client()
    if client is None:
        return None

    s = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    with client:
        try:
            resp = client.get(
                f"https://api.github.com/repos/{s.github_repo}/pulls",
                params={"state": "closed", "sort": "updated",
                        "direction": "desc", "per_page": 20},
            )
            resp.raise_for_status()
            items: list[str] = []
            for pr in resp.json():
                merged_at = pr.get("merged_at")
                if not merged_at:
                    continue
                try:
                    merged_dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                except Exception:
                    continue
                if merged_dt >= cutoff:
                    items.append(_parse_pr(pr))
            return Signal(
                kind="event",
                source=SignalSource(collector=name, provenance="medium"),
                data={"items": items[:10], "recent_merge_count": len(items)},
            )
        except Exception:
            return None


# ---------- Datadog ----------
def _dd_headers() -> dict:
    s = get_settings()
    return {"DD-API-KEY": s.datadog_api_key, "DD-APPLICATION-KEY": s.datadog_app_key}


def _dd_metric(query: str) -> float | None:
    s = get_settings()
    now = int(time.time())
    url = f"https://api.{s.datadog_site}/api/v1/query"
    try:
        r = httpx.get(url, params={"from": now - 600, "to": now, "query": query},
                      headers=_dd_headers(), timeout=s.datadog_timeout)
        r.raise_for_status()
        return parse_dd_series_last(r.json())
    except Exception:
        return None


def _dd_logs(alert: AlertPayload) -> list[str]:
    s = get_settings()
    url = f"https://api.{s.datadog_site}/api/v2/logs/events/search"
    body = {"filter": {"query": f"pod_name:{alert.service}*", "from": "now-15m", "to": "now"},
            "page": {"limit": 8}}
    try:
        r = httpx.post(url, json=body, headers=_dd_headers(), timeout=s.datadog_timeout)
        r.raise_for_status()
        return parse_dd_logs(r.json())
    except Exception:
        return []


def datadog_collect(name: str, alert: AlertPayload) -> Signal | None:
    pid, _, _ = match_pattern(alert.alertname)
    if name == "logs":
        lines = _dd_logs(alert)
        if lines:
            return Signal(kind="log", source=SignalSource(collector=name, provenance="low"),
                          data={"lines": lines})
        return None
    facts: dict[str, Any] = {}
    if name == "metrics" and pid == "OOMKill":
        v = _dd_metric(f"avg:kubernetes.memory.usage{{pod_name:{alert.service}*}}")
        if v is not None:
            facts["memory_usage_bytes"] = int(v)
    elif name == "metrics" and pid == "HighLatency":
        v = _dd_metric(f"avg:trace.http.request.duration.by.service.99p{{service:{alert.service}}}")
        if v is not None:
            facts["p99_latency_s"] = round(v, 3)
    elif name == "saturation":
        v = _dd_metric(f"avg:kubernetes.cpu.usage.total{{pod_name:{alert.service}*}}")
        if v is not None:
            facts["cpu_usage"] = round(v, 3)
    if not facts:
        return None
    return Signal(kind="metric", source=SignalSource(collector=name, provenance="high"), data=facts)
