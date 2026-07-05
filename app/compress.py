# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Signal compression: deduplicate, preserve provenance, build facts + a token-budgeted bundle.
Core dedup/provenance approach authored by Kimi; fact/budget shaping by Claude."""
from __future__ import annotations
import hashlib
import json
from .models import Signal, CompressedSignals, AlertPayload

_CHARS_PER_TOKEN = 4


def _est_tokens(obj) -> int:
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return max(1, (len(s) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def compress_signals(alert: AlertPayload, pattern_id: str, signals: list[Signal],
                     hard_cap: int) -> CompressedSignals:
    # Deduplicate by content hash (Kimi)
    seen: set[str] = set()
    deduped: list[Signal] = []
    for sig in signals:
        h = hashlib.sha256(f"{sig.kind}:{sig.source.collector}:{sig.data}".encode()).hexdigest()[:16]
        if h not in seen:
            seen.add(h)
            deduped.append(sig)

    facts: list[dict] = []
    recent_logs: list[str] = []
    recent_events: list[str] = []
    kind_counts: dict[str, int] = {}
    for sig in deduped:
        kind_counts[sig.kind] = kind_counts.get(sig.kind, 0) + 1
        if sig.kind == "log":
            recent_logs = list(sig.data.get("lines", []))[-8:]
        elif sig.kind == "event":
            recent_events = list(sig.data.get("items", []))[-5:]
        elif isinstance(sig.data, dict):
            for k, v in sig.data.items():
                facts.append({"signal": sig.source.collector, "key": k, "value": v,
                              "provenance": sig.source.provenance})

    obj = {"facts": facts, "recent_logs": recent_logs, "recent_events": recent_events}
    tokens_before = _est_tokens(obj)
    truncated = False
    # Deterministic truncation: drop oldest log lines first, then long string facts.
    while _est_tokens(obj) > hard_cap and recent_logs:
        recent_logs.pop(0); truncated = True
    obj["recent_logs"] = recent_logs
    if _est_tokens(obj) > hard_cap:
        for f in facts:
            if isinstance(f["value"], str) and len(f["value"]) > 200:
                f["value"] = f["value"][:200] + "…"; truncated = True

    return CompressedSignals(
        pattern_id=pattern_id, alert_id=alert.alert_id, service=alert.service,
        namespace=alert.namespace, cluster=alert.cluster, alert=alert.alertname,
        severity=alert.severity, facts=facts, recent_logs=recent_logs,
        recent_events=recent_events, summary={"kind_counts": kind_counts, "signal_count": len(deduped)},
        meta={"tokens_before": tokens_before, "tokens_after": _est_tokens(obj), "truncated": truncated},
    )
