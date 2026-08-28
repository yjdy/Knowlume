from __future__ import annotations

import json
from typing import Any

from knowlume.constants import INTERFACE_VERSION


def success_envelope(command: str, data: Any) -> dict[str, Any]:
    return {
        "interface_version": INTERFACE_VERSION,
        "command": command,
        "success": True,
        "exit_code": 0,
        "data": data,
        "warnings": [],
        "errors": [],
    }


def error_envelope(
    command: str,
    *,
    exit_code: int,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "interface_version": INTERFACE_VERSION,
        "command": command,
        "success": False,
        "exit_code": exit_code,
        "data": None,
        "warnings": [],
        "errors": [{"code": code, "message": message}],
    }


def render_json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
