# Copyright (c) 2025 Control Network. All rights reserved. Provided for evaluation only.
"""Zero Data Retention helpers — in-RAM only; sensitive buffers overwritten in place."""
from __future__ import annotations
import ctypes
from typing import Any


def wipe(buf: bytearray) -> None:
    if isinstance(buf, bytearray) and len(buf):
        ctypes.memset((ctypes.c_char * len(buf)).from_buffer(buf), 0, len(buf))


def scrub(obj: Any) -> None:
    """Drop references / overwrite bytearrays in a dict or pydantic model dump."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, bytearray):
                wipe(v)
            obj[k] = None
        obj.clear()


def verify_no_persistence(paths: list[str]) -> bool:
    import os
    return all(not os.path.exists(p) for p in paths)
