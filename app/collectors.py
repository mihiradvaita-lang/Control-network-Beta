# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Signal collection orchestrator. Sim mode reads the alert's pre-baked raw signals;
real mode dispatches to per-source connectors (Prometheus, Datadog, Kubernetes, GitHub).
Output is a list[Signal] (Kimi model)."""
from __future__ import annotations
import concurrent.futures
from typing import Any
from .config import get_settings
from .models import AlertPayload, Signal, SignalSource

# collector name -> (signal kind, provenance)
_KIND = {
    "metrics": ("metric", "high"),
    "saturation": ("metric", "high"),
    "disk": ("metric", "high"),
    "pod_describe": ("describe", "high"),
    "node_describe": ("describe", "high"),
    "pvc": ("describe", "medium"),
    "deployment": ("deploy", "high"),
    "logs": ("log", "low"),
    "events": ("event", "low"),
    "recent_changes": ("event", "medium"),
}


def _sim_collect(name: str, alert: AlertPayload) -> Signal | None:
    raw = (alert.raw or {}).get(name)
    if raw is None:
        return None
    kind, prov = _KIND.get(name, ("metric", "medium"))
    if name == "logs":
        data: Any = {"lines": list(raw)}
    elif name == "events":
        data = {"items": list(raw)}
    elif name == "recent_changes":
        data = {"items": list(raw.get("items", [])),
                "recent_merge_count": raw.get("recent_merge_count", 0)}
    else:
        data = dict(raw)
    return Signal(kind=kind, source=SignalSource(collector=name, provenance=prov), data=data)


def _real_collect(name: str, alert: AlertPayload) -> Signal | None:
    """Try every configured real source in priority order; return None to let collect()
    fall back to sim. A source is used iff its env is fully configured (per-source
    predicates in Settings). Imported lazily so sim mode never needs heavy deps."""
    s = get_settings()
    try:
        if s.data_mode == "sim":
            return None
        if s.prometheus_enabled:
            from .collectors_real import prometheus_collect
            sig = prometheus_collect(name, alert)
            if sig is not None:
                return sig
        if s.datadog_enabled:
            from .collectors_real import datadog_collect
            sig = datadog_collect(name, alert)
            if sig is not None:
                return sig
        if s.k8s_enabled:
            from .collectors_real import k8s_collect
            sig = k8s_collect(name, alert)
            if sig is not None:
                return sig
        if s.github_enabled:
            from .collectors_real import github_collect
            sig = github_collect(name, alert)
            if sig is not None:
                return sig
    except Exception:
        return None
    return None


def _collect_one(alert: AlertPayload, name: str, real_active: bool) -> Signal | None:
    """Resolve a single collector: real source if configured (best-effort), else sim.
    When a real source was attempted but failed, the sim substitute is marked degraded.
    Never raises (all real-source errors are swallowed inside _real_collect)."""
    sig = None
    attempted_real = False
    if real_active:
        attempted_real = True
        sig = _real_collect(name, alert)    # best-effort, may be None
    if sig is None:
        sig = _sim_collect(name, alert)     # guaranteed fallback
        if sig is not None and attempted_real:
            sig.degraded = True             # real source failed; sim data substituted
    return sig


def collect(alert: AlertPayload, collector_names: list[str]) -> list[Signal]:
    """Per-collector source resolution: real source if configured (best-effort), else sim.
    Sim is the guaranteed fallback so zero-config always works. Never raises.

    Real-mode latency: each collector may make several sequential blocking HTTP calls (e.g.
    OOMKill metrics = 2 Prometheus queries, then k8s pod_describe = list+read). Run serially,
    a 4-collector pattern with all sources timing out stacks into ~25-30s. We fan the
    per-collector work out across a bounded thread pool (worst-case latency collapses to the
    single slowest collector) while PRESERVING the caller's collector order in the output — the
    compressor and report rely on that ordering. Sim mode is pure/instant, so parallelizing it
    is harmless; the single code path keeps this simple."""
    s = get_settings()
    real_active = s.data_mode != "sim" and (
        s.prometheus_enabled or s.datadog_enabled or s.k8s_enabled or s.github_enabled
    )

    # Serial fast path: sim mode (or nothing to do) has no network cost, so skip the pool.
    if not real_active or len(collector_names) <= 1:
        out: list[Signal] = []
        for name in collector_names:
            sig = _collect_one(alert, name, real_active)
            if sig is not None:
                out.append(sig)
        return out

    # Parallel path (real mode, >1 collector): bounded workers, order preserved by index.
    results: list[Signal | None] = [None] * len(collector_names)
    workers = min(len(collector_names), 8)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_idx = {
                pool.submit(_collect_one, alert, name, real_active): idx
                for idx, name in enumerate(collector_names)
            }
            for fut in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[fut]
                try:
                    results[idx] = fut.result()
                except Exception:
                    results[idx] = None   # never raise; a dead collector just yields no signal
    except Exception:
        # Pool creation/scheduling failure must not break triage: fall back to serial.
        return [sig for name in collector_names
                if (sig := _collect_one(alert, name, real_active)) is not None]

    return [sig for sig in results if sig is not None]
