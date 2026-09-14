from __future__ import annotations

from collections.abc import Callable
from typing import Any

from knowlume.domain.values import DomainError
from knowlume.ports.diagnostics import DiagnosticProbePort, ProbeName

PROBES: tuple[ProbeName, ...] = ("vault", "sqlite", "git", "zotero")


def diagnostic_exit_code(code: str) -> int:
    if "UNSAFE" in code:
        return 6
    if code in {
        "INDEX_BUSY",
        "INDEX_SOURCE_CHANGED",
        "VAULT_LOCKED",
        "VAULT_RECOVERY_REQUIRED",
        "VAULT_RECOVERY_FAILED",
        "VAULT_WRITE_CONFLICT",
    }:
        return 4
    if "UNAVAILABLE" in code or code == "INDEX_NOT_FOUND":
        return 5
    return 3


def diagnostic_report(
    probes: tuple[str, ...],
    *,
    runner: DiagnosticProbePort,
    installation: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    if not probes or any(probe not in PROBES for probe in probes):
        raise DomainError(
            "DOCTOR_ARGUMENT_INVALID", "choose explicit vault, sqlite, git or zotero probes"
        )
    selected = tuple(name for name in PROBES if name in probes)
    legacy = installation()
    checks: list[dict[str, Any]] = []
    for check in legacy["checks"]:
        checks.append(
            {
                "name": check["name"],
                "status": "passed" if check["success"] else "failed",
                "code": "DOCTOR_CHECK_PASSED"
                if check["success"]
                else "DOCTOR_INSTALLATION_INVALID",
                "message": "Installation check passed."
                if check["success"]
                else "Installation check failed; inspect the installed package.",
                "exit_code": 0 if check["success"] else 3,
            }
        )
    for name in PROBES:
        if name not in selected:
            checks.append(
                {
                    "name": name,
                    "status": "skipped",
                    "code": "DOCTOR_CHECK_SKIPPED",
                    "message": "Probe was not requested.",
                    "exit_code": 0,
                }
            )
            continue
        try:
            runner.probe(name)
            checks.append(
                {
                    "name": name,
                    "status": "passed",
                    "code": "DOCTOR_CHECK_PASSED",
                    "message": "Requested local probe passed.",
                    "exit_code": 0,
                }
            )
        except DomainError as error:
            code = diagnostic_exit_code(error.code)
            checks.append(
                {
                    "name": name,
                    "status": "unavailable" if code == 5 else "failed",
                    "code": error.code,
                    "message": "Requested probe did not pass; inspect its diagnostic code locally.",
                    "exit_code": code,
                }
            )
        except Exception:
            checks.append(
                {
                    "name": name,
                    "status": "failed",
                    "code": "DOCTOR_PROBE_FAILED",
                    "message": "Requested probe could not be completed.",
                    "exit_code": 3,
                }
            )
    failures = {check["exit_code"] for check in checks if check["exit_code"]}
    exit_code = next((code for code in (6, 4, 3, 5) if code in failures), 0)
    return {
        "report_version": 2,
        "healthy": exit_code == 0,
        "versions": legacy["versions"],
        "probes": list(selected),
        "checks": checks,
    }, exit_code
