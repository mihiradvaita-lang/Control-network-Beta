# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Pattern matching: alertname -> (pattern_id, ordered collectors, title). Config-driven."""
from __future__ import annotations
from .config import load_patterns


def match_pattern(alertname: str) -> tuple[str | None, list[str], str]:
    patterns = load_patterns()
    al = (alertname or "").lower()
    for key, spec in patterns.items():
        for trig in spec.get("triggers", []):
            if trig.lower() == al:
                return key, spec["collectors"], spec.get("title", key)
    for key, spec in patterns.items():
        if key.lower() in al or any(t.lower() in al for t in spec.get("triggers", [])):
            return key, spec["collectors"], spec.get("title", key)
    return None, [], ""
