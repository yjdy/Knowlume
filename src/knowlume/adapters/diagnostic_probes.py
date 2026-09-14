from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from knowlume.adapters.filesystem import FilesystemVault, checksum_file
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.domain.values import DomainError
from knowlume.ports.diagnostics import ProbeName
from knowlume.ports.vault import Vault


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


def _vault_probe(vault: Vault, validate: Callable[[Vault], None]) -> None:
    if any(_probe_location(vault, vault.path("state") / "transactions").iterdir()):
        raise DomainError(
            "VAULT_RECOVERY_REQUIRED", "an unfinished transaction requires explicit recovery"
        )
    if any(_probe_location(vault, vault.path("state") / "locks").iterdir()):
        raise DomainError("VAULT_LOCKED", "Vault has an active or unresolved writer lock")
    validate(vault)


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


class LocalDiagnosticProbes:
    """Read-only local probe adapter; construction never discovers a Vault or contacts an API."""

    def __init__(
        self, *, validate_vault: Callable[[Vault], None], explicit_vault: Path | None = None
    ) -> None:
        self._explicit_vault = explicit_vault
        self._validate_vault = validate_vault
        self._vault: Vault | None = None

    def _discover(self) -> Vault:
        if self._vault is None:
            try:
                self._vault = FilesystemVault().discover(
                    explicit=self._explicit_vault, cwd=Path.cwd()
                )
            except (OSError, UnicodeError) as error:
                raise DomainError(
                    "VAULT_INVALID", "Vault configuration could not be read or decoded"
                ) from error
        return self._vault

    def probe(self, name: ProbeName) -> None:
        if name == "vault":
            _vault_probe(self._discover(), self._validate_vault)
        elif name == "sqlite":
            _sqlite_probe(self._discover())
        elif name == "git":
            _git_probe()
        elif name == "zotero":
            _zotero_probe()
        else:
            raise DomainError("DOCTOR_ARGUMENT_INVALID", "unsupported diagnostic probe")
