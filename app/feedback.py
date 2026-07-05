# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Feedback: in-RAM only (ZDR-safe); flushed to stdout on shutdown."""
from __future__ import annotations
import atexit, json
from collections import deque
from typing import Any

_BUF: deque[dict[str, Any]] = deque(maxlen=500)

def record(incident_id: str, pattern: str, vote: str, note: str = "") -> dict:
    _BUF.append({"incident": incident_id, "pattern": pattern, "vote": vote, "note": note[:280]})
    return {"ok": True, "count": len(_BUF)}

def snapshot() -> list[dict]:
    return list(_BUF)

@atexit.register
def _flush() -> None:
    if _BUF:
        print("[CN feedback flush on shutdown] " + json.dumps(list(_BUF)))
