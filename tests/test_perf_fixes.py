"""Regression tests for AUDIT ITERATION 2 (efficiency/performance) fixes.

These lock in behavior that could silently regress if someone reverts a perf change:
  1. collect() preserves collector ORDER even when running collectors in parallel.
  2. collect() NEVER raises, even if a per-collector resolution blows up.
  3. Parallel collect actually runs concurrently (worst-case latency ~= slowest collector,
     not the sum) when real sources are active.
  4. The startup LLM model check is backgrounded (non-blocking).
"""
from __future__ import annotations

import time
from unittest import mock

from app.collectors import collect, _collect_one
from app.config import get_settings
from app.models import AlertPayload


def _clear_settings_cache():
    get_settings.cache_clear()


def _alert(names_pattern: str = "KubePodOOMKilled") -> AlertPayload:
    return AlertPayload(
        alert_id="INC-perf", alertname=names_pattern, severity="critical",
        service="payment-service", namespace="prod", cluster="c1",
        message="oom", raw={},
    )


# --- 1. order preservation -------------------------------------------------

def test_collect_preserves_order_serial_sim():
    """Sim mode (serial path): output Signals follow the requested collector order."""
    _clear_settings_cache()
    raw = {"metrics": {"a": 1}, "pod_describe": {"b": 2},
           "deployment": {"c": 3}, "recent_changes": {"items": [], "recent_merge_count": 0}}
    alert = AlertPayload(alert_id="X", alertname="KubePodOOMKilled", severity="critical",
                         service="svc", namespace="prod", cluster="c", message="", raw=raw)
    names = ["metrics", "pod_describe", "deployment", "recent_changes"]
    sigs = collect(alert, names)
    assert [s.source.collector for s in sigs] == names


def test_collect_preserves_order_parallel_real():
    """Real mode (parallel path): even with out-of-order completion, output order == input order.
    We stub _collect_one so each collector sleeps an amount that INVERTS the input order —
    if the result were ordered by completion, the assertion would fail."""
    _clear_settings_cache()
    names = ["metrics", "pod_describe", "deployment", "recent_changes"]
    # sleep longest for the first, shortest for the last => completion order is reversed
    delays = {"metrics": 0.20, "pod_describe": 0.15, "deployment": 0.10, "recent_changes": 0.05}

    def fake_one(alert, name, real_active):
        assert real_active is True
        time.sleep(delays[name])
        from app.models import Signal, SignalSource
        return Signal(kind="metric", source=SignalSource(collector=name, provenance="high"),
                      data={"n": name})

    fake_settings = mock.Mock()
    fake_settings.data_mode = "prometheus"
    fake_settings.prometheus_enabled = True
    fake_settings.datadog_enabled = False
    fake_settings.k8s_enabled = False
    fake_settings.github_enabled = False

    with mock.patch("app.collectors.get_settings", return_value=fake_settings), \
         mock.patch("app.collectors._collect_one", side_effect=fake_one):
        sigs = collect(_alert(), names)
    assert [s.source.collector for s in sigs] == names


def test_collect_parallel_is_concurrent():
    """Wall-clock of a 4-collector parallel run is close to the slowest single collector,
    not the sum. Guards against an accidental revert to serial in real mode."""
    _clear_settings_cache()
    names = ["metrics", "pod_describe", "deployment", "recent_changes"]

    def slow_one(alert, name, real_active):
        time.sleep(0.15)
        from app.models import Signal, SignalSource
        return Signal(kind="metric", source=SignalSource(collector=name, provenance="high"),
                      data={})

    fake_settings = mock.Mock()
    fake_settings.data_mode = "prometheus"
    fake_settings.prometheus_enabled = True
    fake_settings.datadog_enabled = False
    fake_settings.k8s_enabled = False
    fake_settings.github_enabled = False

    with mock.patch("app.collectors.get_settings", return_value=fake_settings), \
         mock.patch("app.collectors._collect_one", side_effect=slow_one):
        t0 = time.monotonic()
        sigs = collect(_alert(), names)
        elapsed = time.monotonic() - t0
    assert len(sigs) == 4
    # serial would be ~0.60s; parallel should be well under 0.35s.
    assert elapsed < 0.35, f"expected concurrent execution, took {elapsed:.3f}s"


# --- 2. never raises -------------------------------------------------------

def test_collect_never_raises_when_collector_errors():
    """If a per-collector resolution raises inside the pool, collect() swallows it and
    returns the successful signals rather than propagating."""
    _clear_settings_cache()
    names = ["metrics", "pod_describe", "deployment"]

    def flaky_one(alert, name, real_active):
        if name == "pod_describe":
            raise RuntimeError("boom")
        from app.models import Signal, SignalSource
        return Signal(kind="metric", source=SignalSource(collector=name, provenance="high"),
                      data={})

    fake_settings = mock.Mock()
    fake_settings.data_mode = "prometheus"
    fake_settings.prometheus_enabled = True
    fake_settings.datadog_enabled = False
    fake_settings.k8s_enabled = False
    fake_settings.github_enabled = False

    with mock.patch("app.collectors.get_settings", return_value=fake_settings), \
         mock.patch("app.collectors._collect_one", side_effect=flaky_one):
        sigs = collect(_alert(), names)
    # the two good collectors survive, in order; the raising one is simply dropped
    assert [s.source.collector for s in sigs] == ["metrics", "deployment"]


def test_collect_empty_collector_list_is_safe():
    _clear_settings_cache()
    assert collect(_alert(), []) == []


# --- 3. startup model check is non-blocking --------------------------------

def test_startup_llm_check_is_backgrounded():
    """The startup hook must not block: it should spawn a daemon thread and return
    immediately, even if the underlying probe would sleep for a long time."""
    import app.main as main

    started = {"thread": None}

    def slow_probe():
        time.sleep(5.0)  # simulate a hung network probe

    with mock.patch.object(main, "_run_llm_model_check", side_effect=slow_probe):
        t0 = time.monotonic()
        main._verify_llm_model()
        elapsed = time.monotonic() - t0
    # returns effectively instantly despite the 5s probe
    assert elapsed < 0.5, f"startup hook blocked for {elapsed:.3f}s"
