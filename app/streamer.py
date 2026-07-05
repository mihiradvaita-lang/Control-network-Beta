# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""SSE event formatting for the triage stream."""
from __future__ import annotations
import json
from typing import Any


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
