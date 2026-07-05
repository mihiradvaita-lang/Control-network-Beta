# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Health / readiness payload."""
from __future__ import annotations
from . import __version__
from .config import get_settings


def _data_source(s) -> str:
    if s.data_mode == "prometheus" and s.prometheus_enabled:
        return "prometheus"
    if s.data_mode == "datadog" and s.datadog_enabled:
        return "datadog"
    return "sim"


def health() -> dict:
    s = get_settings()
    return {"status": "ok", "version": __version__, "zdr": s.zdr_mode,
            "llm": s.active_provider, "data_source": _data_source(s)}
