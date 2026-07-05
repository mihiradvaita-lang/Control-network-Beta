# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""The triage pipeline wiring (Kimi architecture): alert -> pattern -> collect -> compress -> narrative -> report.

Latency contract (P0-1/P0-2): `prepare()` is pure deterministic/fast work (pattern match,
collect, compress) and must never touch the network. `stream_triage_events()` is the single
source of truth for the SSE event sequence emitted by GET /api/triage/stream, refactored out
of app/main.py so it is directly unit-testable without booting a server.
"""
from __future__ import annotations
import time
from typing import Any, Iterator
from .config import get_settings, load_skill_md
from .models import AlertPayload
from .patterns import match_pattern
from .collectors import collect
from .compress import compress_signals
from .narrative import stream_narrative_tracked
from .report import assemble, humanized_facts
from .streamer import sse


def alert_from_scenario(scn: dict) -> AlertPayload:
    return AlertPayload(
        alert_id=scn.get("id", "INC"), alertname=scn.get("alertname", ""),
        severity=scn.get("severity", "warning"), service=scn.get("service"),
        namespace=scn.get("namespace"), cluster=scn.get("cluster"),
        message=scn.get("summary", ""), raw=scn.get("raw", {}),
    )


def prepare(alert: AlertPayload):
    pid, cols, title = match_pattern(alert.alertname)
    signals = collect(alert, cols) if pid else []
    c = compress_signals(alert, pid or "Unknown", signals, get_settings().token_hard_cap)
    return pid, title, c


def triage_full(alert: AlertPayload) -> dict[str, Any]:
    pid, title, c = prepare(alert)
    gen, run = stream_narrative_tracked(c, load_skill_md())
    narrative = "".join(gen)  # run.used_fallback is authoritative only after full consumption
    return {
        "incident_id": alert.alert_id, "pattern": pid,
        "report_markdown": assemble(c, title, narrative),
        "context_meta": c.meta,
        "llm": "deterministic" if run.used_fallback else get_settings().active_provider,
    }


def stream_triage_events(scn: dict) -> Iterator[str]:
    """Generator of fully-formatted SSE frames for one triage run, given a raw scenario dict
    (as returned by scenarios.get_scenario / the `incident` body of /api/triage). This is what
    GET /api/triage/stream wraps in a StreamingResponse; kept here so tests can drive it
    in-process without a running server.

    Ordering guarantee (P0-1/P0-2): phase(DETECTED) -> phase(CORRELATING) -> meta -> facts ->
    phase(ANALYZING) -> token(s) -> [notice if fallback] -> phase(DONE) -> done. Everything up
    to and including `facts` is synchronous, deterministic, and never waits on a network call.
    """
    t0 = time.monotonic()
    try:
        alert = alert_from_scenario(dict(scn))

        # --- deterministic phase: pattern match (instant) ---
        pid, cols, title = match_pattern(alert.alertname)
        yield sse("phase", {"phase": "DETECTED", "label": "Alert matched"})

        # --- deterministic phase: collect + compress (fast, local, no network) ---
        signals = collect(alert, cols) if pid else []
        c = compress_signals(alert, pid or "Unknown", signals, get_settings().token_hard_cap)
        yield sse("phase", {"phase": "CORRELATING", "label": "Signals collected & compressed"})

        prep_ms = int((time.monotonic() - t0) * 1000)

        # meta kept verbatim for backward compat with existing consumers
        yield sse("meta", {"pattern": pid, "title": title, "context_meta": c.meta})
        # facts: new, richer event -- header metadata + humanized evidence, pre-LLM
        yield sse("facts", {
            "pattern": pid, "title": title,
            "service": c.service, "namespace": c.namespace, "cluster": c.cluster,
            "severity": c.severity, "alert_id": c.alert_id,
            "context_meta": c.meta,
            "facts": humanized_facts(c),
        })

        # --- narrative phase: may hit the network; never blocks the facts above ---
        yield sse("phase", {"phase": "ANALYZING", "label": "Generating analysis"})
        ttft_ms = None
        parts: list[str] = []
        gen, run = stream_narrative_tracked(c, load_skill_md())
        for chunk in gen:
            if ttft_ms is None:
                ttft_ms = int((time.monotonic() - t0) * 1000)
            parts.append(chunk)
            yield sse("token", {"t": chunk})
        if ttft_ms is None:  # narrative produced nothing (shouldn't normally happen)
            ttft_ms = int((time.monotonic() - t0) * 1000)

        if run.used_fallback:
            yield sse("notice", {"level": "warning", "message": "AI unavailable — deterministic analysis shown"})

        report = assemble(c, title, "".join(parts))
        total_ms = int((time.monotonic() - t0) * 1000)
        yield sse("phase", {"phase": "DONE", "label": "Report ready"})
        yield sse("done", {
            "report_markdown": report,
            "elapsed_ms": total_ms,
            "total_ms": total_ms,
            "prep_ms": prep_ms,
            "ttft_ms": ttft_ms,
            "llm": get_settings().active_provider if not run.used_fallback else "deterministic",
        })
    except Exception as e:  # noqa - the stream must never crash the connection uncaught
        # Sanitized: never echo str(e) — exception messages from httpx/etc. can embed the
        # request URL (e.g. a secret webhook URL) or other internal detail. Type name only.
        yield sse("error", {"error": type(e).__name__})
