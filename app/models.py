# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""ZDR data models — every instance is ephemeral, never persisted. (Kimi design.)"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field

Provenance = Literal["high", "medium", "low"]


class AlertPayload(BaseModel):
    """Incoming alert from monitoring/alertmanager."""
    alert_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "prometheus"
    alertname: str = ""
    severity: str = "warning"
    service: str | None = None
    namespace: str | None = None
    cluster: str | None = None
    message: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class SignalSource(BaseModel):
    collector: str
    provenance: Provenance = "medium"


class Signal(BaseModel):
    kind: str                       # metric | describe | deploy | log | event
    source: SignalSource
    data: Any                       # flat dict, or {"lines"/"items": [...]}
    degraded: bool = False          # True when a real source failed and sim data was used


class CompressedSignals(BaseModel):
    pattern_id: str
    alert_id: str
    service: str | None = None
    namespace: str | None = None
    cluster: str | None = None
    alert: str = ""
    severity: str = "warning"
    facts: list[dict] = Field(default_factory=list)        # {signal,key,value,provenance}
    recent_logs: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)               # tokens_before/after, truncated
