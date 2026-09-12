from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from knowlume.adapters.filesystem import FilesystemVault, checksum_file
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.application.scanning import scan_vault
from knowlume.application.vault import VaultService
from knowlume.doctor import doctor_report
from knowlume.domain.values import DomainError
from knowlume.ports.vault import Vault

PROBES = ("vault", "sqlite", "git", "zotero")


def _git_probe() -> None:
    executable = shutil.which("git")
    if executable is None:
        raise DomainError("GIT_CAPABILITY_UNAVAILABLE", "Git is not installed")
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DomainError(
            "GIT_CAPABILITY_UNAVAILABLE", "Git version check is unavailable"
        ) from error
    if result.returncode or not re.fullmatch(
        rb"git version [0-9][a-zA-Z0-9.\-+ ()]*\r?\n?", result.stdout
    ):
        raise DomainError("GIT_RESPONSE_INVALID", "Git returned an invalid version response")


def _zotero_probe() -> None:
    from knowlume.adapters.zotero_local import ZoteroLocalApi

    ZoteroLocalApi().probe()


def _probe_location(vault: Vault, path: Path) -> Path:
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(vault.root)
        if resolved != path.absolute():
            raise ValueError("alias")
    except (OSError, ValueError) as error:
        raise DomainError(
            "VAULT_PATH_UNSAFE", "probe target has an unsafe resolved path"
        ) from error
    return path


def _vault_probe(vault: Vault) -> None:
    if any(_probe_location(vault, vault.path("state") / "transactions").iterdir()):
        raise DomainError(
            "VAULT_RECOVERY_REQUIRED", "an unfinished transaction requires explicit recovery"
        )
    if any(_probe_location(vault, vault.path("state") / "locks").iterdir()):
        raise DomainError("VAULT_LOCKED", "Vault has an active or unresolved writer lock")
    scan = scan_vault(vault)
    if not scan.healthy:
        unsafe = any(finding.code == "VAULT_PATH_UNSAFE" for finding in scan.findings)
        raise DomainError(
            "VAULT_PATH_UNSAFE" if unsafe else "VAULT_INVALID",
            "Vault scan has blocking findings; inspect scan locally",
        )


def _sqlite_probe(vault: Vault) -> None:
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE VIRTUAL TABLE capability USING fts5(text)")
    except sqlite3.Error as error:
        raise DomainError(
            "SQLITE_CAPABILITY_UNAVAILABLE", "SQLite FTS5 capability is unavailable"
        ) from error
    projection = SQLiteProjection()
    database = _probe_location(vault, projection.database_path(vault))
    before = checksum_file(database)
    report = projection.status(vault, immutable=True)
    after = checksum_file(database)
    if before != after:
        raise DomainError("INDEX_BUSY", "index changed during read-only inspection")
    errors = {
        "missing": ("INDEX_NOT_FOUND", "index is missing; build it explicitly"),
        "incompatible": (
            "INDEX_INCOMPATIBLE",
            "index versions are incompatible; rebuild explicitly",
        ),
        "stale": ("INDEX_SOURCE_CHANGED", "index is stale; refresh it explicitly"),
        "corrupt": ("INDEX_CORRUPT", "index could not be validated"),
        "busy": ("INDEX_BUSY", "index has journal or WAL state; inspect its writer first"),
    }
    if str(report["state"]) in errors:
        raise DomainError(*errors[str(report["state"])])


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
    explicit_vault: Path | None = None,
    installation: Callable[[], dict[str, Any]] = doctor_report,
    git_probe: Callable[[], None] | None = None,
    zotero_probe: Callable[[], None] | None = None,
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
    vault = None
    vault_error = None
    if {"vault", "sqlite"} & set(selected):
        try:
            vault = VaultService(FilesystemVault()).discover(explicit=explicit_vault)
        except DomainError as error:
            vault_error = error
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
            if name in {"vault", "sqlite"}:
                if vault_error is not None:
                    raise vault_error
                assert vault is not None
                (_vault_probe if name == "vault" else _sqlite_probe)(vault)
            elif name == "git":
                (git_probe or _git_probe)()
            else:
                (zotero_probe or _zotero_probe)()
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
