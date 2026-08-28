from __future__ import annotations

import sys
from typing import Any

from platformdirs import user_cache_dir, user_config_dir, user_log_dir, user_state_dir

from knowlume.constants import (
    DISTRIBUTION_NAME,
    READABLE_OBJECT_CONTRACT_RANGE,
    SUPPORTED_PYTHON_MAX_EXCLUSIVE,
    SUPPORTED_PYTHON_MIN,
    WRITABLE_OBJECT_CONTRACT_RANGE,
)
from knowlume.resources import validate_required_assets
from knowlume.versioning import version_report


def doctor_report() -> dict[str, Any]:
    python_version = sys.version_info[:3]
    supported = SUPPORTED_PYTHON_MIN <= python_version < SUPPORTED_PYTHON_MAX_EXCLUSIVE
    asset_errors = validate_required_assets()
    checks = [
        {
            "name": "python",
            "success": supported,
            "detail": ".".join(str(part) for part in python_version),
        },
        {
            "name": "package-assets",
            "success": not asset_errors,
            "detail": "ok" if not asset_errors else "; ".join(asset_errors),
        },
    ]
    return {
        "report_version": 1,
        "healthy": all(check["success"] for check in checks),
        "versions": version_report(),
        "contract_compatibility": {
            "readable": list(READABLE_OBJECT_CONTRACT_RANGE),
            "writable": list(WRITABLE_OBJECT_CONTRACT_RANGE),
        },
        "checks": checks,
        "user_paths": {
            "config": user_config_dir(DISTRIBUTION_NAME, appauthor=False),
            "cache": user_cache_dir(DISTRIBUTION_NAME, appauthor=False),
            "state": user_state_dir(DISTRIBUTION_NAME, appauthor=False),
            "logs": user_log_dir(DISTRIBUTION_NAME, appauthor=False),
        },
    }
