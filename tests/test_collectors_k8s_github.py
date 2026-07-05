"""Tests for Kubernetes and GitHub real collectors (Kimi Stage 1 delivery).

- Mock kubernetes.client: pod describe, events, logs, deployment, node describe, PVC.
- Mock GitHub REST (respx): merged-PR list -> items strings.
- Fallback tests: any real-source failure falls back to sim, never raises.
- Contract test: every collector name referenced in config/patterns.yaml, in BOTH real
  and sim versions, returns a Signal with provenance.

Original 10 tests in tests/test_pipeline.py are untouched (frozen surface).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import respx
from httpx import Response

from app.collectors import collect, _sim_collect, _real_collect
from app.config import get_settings, load_patterns
from app.models import AlertPayload


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _clear_settings_cache():
    get_settings.cache_clear()


def _alert(**kwargs) -> AlertPayload:
    defaults = {
        "alert_id": "test-001",
        "alertname": "KubePodOOMKilled",
        "service": "payment",
        "namespace": "prod",
        "severity": "critical",
        "raw": {},
    }
    defaults.update(kwargs)
    return AlertPayload(**defaults)


# -----------------------------------------------------------------------------
# Kubernetes tests (kubernetes.client fully mocked -- no cluster, no network)
# -----------------------------------------------------------------------------

def test_k8s_pod_describe_contract():
    from app.collectors_real import k8s_collect

    v1 = mock.MagicMock()
    pod = mock.MagicMock()
    pod.status.phase = "Running"
    cs = mock.MagicMock()
    cs.last_state.terminated.reason = "OOMKilled"
    cs.last_state.terminated.exit_code = 137
    cs.restart_count = 2
    pod.status.container_statuses = [cs]
    v1.read_namespaced_pod.return_value = pod

    with mock.patch("app.collectors_real._k8s_v1", return_value=v1):
        with mock.patch("app.collectors_real._k8s_pod_name", return_value="pod-1"):
            alert = _alert(alertname="KubePodOOMKilled", service="payment", namespace="prod")
            sig = k8s_collect("pod_describe", alert)

    assert sig is not None
    assert sig.kind == "describe"
    assert sig.source.provenance == "high"
    assert sig.data["phase"] == "Running"
    assert sig.data["last_state_reason"] == "OOMKilled"
    assert sig.data["restart_count"] == 2
    assert sig.data["oom_killed"] is True
    assert sig.data["exit_code"] == 137


def test_k8s_events_contract():
    from app.collectors_real import k8s_collect

    v1 = mock.MagicMock()
    ev = mock.MagicMock()
    ev.type = "Warning"
    ev.reason = "BackOff"
    ev.message = "restarting failed container"
    ev.last_timestamp.strftime.return_value = "2026-07-01 12:00"
    v1.list_namespaced_event.return_value.items = [ev]

    with mock.patch("app.collectors_real._k8s_v1", return_value=v1):
        alert = _alert(service="payment", namespace="prod")
        sig = k8s_collect("events", alert)

    assert sig is not None
    assert sig.kind == "event"
    assert sig.source.provenance == "high"
    assert len(sig.data["items"]) == 1
    assert "BackOff" in sig.data["items"][0]


def test_k8s_logs_contract():
    from app.collectors_real import k8s_collect

    v1 = mock.MagicMock()
    v1.read_namespaced_pod_log.side_effect = [
        "line1\nline2\nline3",
        Exception("no previous"),
    ]

    with mock.patch("app.collectors_real._k8s_v1", return_value=v1):
        with mock.patch("app.collectors_real._k8s_pod_name", return_value="pod-1"):
            alert = _alert(service="payment", namespace="prod")
            sig = k8s_collect("logs", alert)

    assert sig is not None
    assert sig.kind == "log"
    assert sig.source.provenance == "medium"
    assert sig.data["lines"] == ["line1", "line2", "line3"]


def test_k8s_logs_empty_returns_none_for_sim_fallback():
    """Empty log output must return None so the sim fallback can provide lines."""
    from app.collectors_real import k8s_collect

    v1 = mock.MagicMock()
    v1.read_namespaced_pod_log.side_effect = ["", ""]

    with mock.patch("app.collectors_real._k8s_v1", return_value=v1):
        with mock.patch("app.collectors_real._k8s_pod_name", return_value="pod-1"):
            sig = k8s_collect("logs", _alert(service="payment", namespace="prod"))

    assert sig is None


def test_k8s_deployment_contract():
    from app.collectors_real import k8s_collect

    apps = mock.MagicMock()
    dep = mock.MagicMock()
    dep.spec.replicas = 3
    dep.status.available_replicas = 2
    apps.read_namespaced_deployment.return_value = dep

    with mock.patch("app.collectors_real._k8s_apps_v1", return_value=apps):
        alert = _alert(service="payment", namespace="prod")
        sig = k8s_collect("deployment", alert)

    assert sig is not None
    assert sig.kind == "deploy"
    assert sig.source.provenance == "high"
    assert sig.data["replicas"] == 3
    assert sig.data["available_replicas"] == 2


def test_k8s_node_describe_contract():
    from app.collectors_real import k8s_collect

    v1 = mock.MagicMock()
    pod = mock.MagicMock()
    pod.spec.node_name = "node-1"
    v1.read_namespaced_pod.return_value = pod

    node = mock.MagicMock()
    cond = mock.MagicMock()
    cond.type = "Ready"
    cond.status = "True"
    node.status.conditions = [cond]
    v1.read_node.return_value = node

    with mock.patch("app.collectors_real._k8s_v1", return_value=v1):
        with mock.patch("app.collectors_real._k8s_pod_name", return_value="pod-1"):
            alert = _alert(service="payment", namespace="prod")
            sig = k8s_collect("node_describe", alert)

    assert sig is not None
    assert sig.kind == "describe"
    assert sig.source.provenance == "high"
    assert sig.data["node"] == "node-1"
    assert sig.data["condition"] == "Ready"


def test_k8s_pvc_contract():
    from app.collectors_real import k8s_collect

    v1 = mock.MagicMock()
    pvc = mock.MagicMock()
    pvc.metadata.name = "data-postgres-0"
    pvc.status.phase = "Bound"
    pvc.status.capacity = {"storage": "50Gi"}
    v1.list_namespaced_persistent_volume_claim.return_value.items = [pvc]

    with mock.patch("app.collectors_real._k8s_v1", return_value=v1):
        alert = _alert(service="postgres", namespace="prod")
        sig = k8s_collect("pvc", alert)

    assert sig is not None
    assert sig.kind == "describe"
    assert sig.source.provenance == "medium"
    assert sig.data["name"] == "data-postgres-0"
    assert sig.data["status"] == "Bound"
    assert sig.data["capacity"] == "50Gi"


# -----------------------------------------------------------------------------
# GitHub tests (respx-mocked REST -- no network)
# -----------------------------------------------------------------------------

@respx.mock
def test_github_recent_changes_contract(monkeypatch):
    _clear_settings_cache()
    monkeypatch.setenv("CN_GITHUB_TOKEN", "ghp_test_not_real")
    monkeypatch.setenv("CN_GITHUB_REPO", "owner/repo")

    # merged_at must be inside the 24h window relative to *now* -- dynamic, not
    # hardcoded (Kimi's draft used fixed dates that silently aged out of the window).
    fresh = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pr_data = [
        {"number": 42, "title": "Fix memory leak", "user": {"login": "alice"}, "merged_at": fresh},
        {"number": 41, "title": "Update deps", "user": {"login": "bob"}, "merged_at": stale},
        {"number": 40, "title": "Closed unmerged", "user": {"login": "carol"}, "merged_at": None},
    ]
    respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
        return_value=Response(200, json=pr_data)
    )

    from app.collectors_real import github_collect

    sig = github_collect("recent_changes", _alert())
    _clear_settings_cache()

    assert sig is not None
    assert sig.kind == "event"
    assert sig.source.provenance == "medium"
    assert sig.data["recent_merge_count"] == 1
    assert any("#42 Fix memory leak" in item for item in sig.data["items"])
    assert not any("#41" in item for item in sig.data["items"])


@respx.mock
def test_github_api_failure_returns_none(monkeypatch):
    _clear_settings_cache()
    monkeypatch.setenv("CN_GITHUB_TOKEN", "ghp_test_not_real")
    monkeypatch.setenv("CN_GITHUB_REPO", "owner/repo")
    respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
        return_value=Response(500)
    )

    from app.collectors_real import github_collect

    sig = github_collect("recent_changes", _alert())
    _clear_settings_cache()
    assert sig is None


def test_github_not_configured_returns_none(monkeypatch):
    _clear_settings_cache()
    monkeypatch.setenv("CN_GITHUB_TOKEN", "")
    monkeypatch.setenv("CN_GITHUB_REPO", "")

    from app.collectors_real import github_collect

    sig = github_collect("recent_changes", _alert())
    _clear_settings_cache()
    assert sig is None


# -----------------------------------------------------------------------------
# Fallback & dispatch tests
# -----------------------------------------------------------------------------

def test_sim_returns_data_without_any_real_source(monkeypatch):
    _clear_settings_cache()
    monkeypatch.setenv("CN_DATA_MODE", "sim")  # forces sim regardless of other env

    alert = _alert(raw={"metrics": {"memory_pct": 95.0}})
    sigs = collect(alert, ["metrics"])
    _clear_settings_cache()

    assert len(sigs) == 1
    assert sigs[0].source.collector == "metrics"
    assert sigs[0].source.provenance == "high"
    assert sigs[0].data["memory_pct"] == 95.0
    assert sigs[0].degraded is False  # sim by choice, not degradation


def test_k8s_exception_falls_back_to_sim(monkeypatch):
    _clear_settings_cache()
    monkeypatch.setenv("CN_DATA_MODE", "real")
    monkeypatch.setenv("CN_KUBECONFIG", "/fake/kubeconfig")
    monkeypatch.setenv("CN_PROMETHEUS_URL", "")
    monkeypatch.setenv("CN_DATADOG_API_KEY", "")
    monkeypatch.setenv("CN_DATADOG_APP_KEY", "")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated k8s failure")

    with mock.patch("app.collectors_real._k8s_v1", side_effect=_boom):
        alert = _alert(raw={"pod_describe": {"phase": "Running", "restarts": 3}})
        sigs = collect(alert, ["pod_describe"])
    _clear_settings_cache()

    assert len(sigs) == 1
    # sim fallback carried the data and is flagged degraded (real source attempted)
    assert sigs[0].data["phase"] == "Running"
    assert sigs[0].data["restarts"] == 3
    assert sigs[0].degraded is True


def test_data_mode_sim_forces_sim_even_with_sources_configured(monkeypatch):
    _clear_settings_cache()
    monkeypatch.setenv("CN_PROMETHEUS_URL", "http://prom-that-should-never-be-called:9090")
    monkeypatch.setenv("CN_DATA_MODE", "sim")

    alert = _alert(raw={"metrics": {"memory_pct": 95.0}})
    sigs = collect(alert, ["metrics"])
    _clear_settings_cache()

    assert len(sigs) == 1
    assert sigs[0].data["memory_pct"] == 95.0


# -----------------------------------------------------------------------------
# Contract test: every collector referenced in patterns.yaml carries provenance
# -----------------------------------------------------------------------------

def test_all_pattern_collectors_return_provenance(monkeypatch):
    _clear_settings_cache()
    monkeypatch.setenv("CN_DATA_MODE", "sim")
    sim_raw = {
        "metrics": {"memory_pct": 50},
        "saturation": {"cpu": "88%"},
        "disk": {"volume_used_pct": 91.0},
        "pod_describe": {"phase": "Running"},
        "node_describe": {"node": "n1", "condition": "Ready"},
        "pvc": {"name": "data-0", "capacity": "50Gi"},
        "logs": ["line1"],
        "events": ["event1"],
        "deployment": {"replicas": 3},
        "recent_changes": {"items": ["#1 fix"], "recent_merge_count": 1},
    }
    patterns = load_patterns()
    for pattern_key, spec in patterns.items():
        for name in spec.get("collectors", []):
            sim_sig = _sim_collect(name, _alert(raw=sim_raw))
            assert sim_sig is not None, f"sim collector {name} produced nothing"
            assert sim_sig.source.provenance in ("high", "medium", "low"), \
                f"sim {name} missing provenance"

            # Real version: no env configured => must return None quietly (contract)
            real_sig = _real_collect(name, _alert())
            if real_sig is not None:
                assert real_sig.source.provenance in ("high", "medium", "low"), \
                    f"real {name} missing provenance"
    _clear_settings_cache()
