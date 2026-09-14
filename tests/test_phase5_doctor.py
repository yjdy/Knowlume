from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_phase5_ai import ROOT, snapshot
from test_phase5_ai import vault as vault
from test_phase5_contracts import validator
from typer.testing import CliRunner

import knowlume.application.diagnostics as diagnostics
from knowlume.adapters.diagnostic_probes import LocalDiagnosticProbes
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.adapters.zotero_local import ZoteroLocalApi
from knowlume.application.scanning import validate_vault_health
from knowlume.cli import app
from knowlume.domain.values import DomainError
from knowlume.ports.diagnostics import ProbeName
from knowlume.ports.vault import Vault
from knowlume.versioning import version_report


class StubProbes:
    def __init__(self, callbacks: dict[ProbeName, Callable[[], None]]) -> None:
        self.callbacks = callbacks

    def probe(self, name: ProbeName) -> None:
        self.callbacks[name]()


def installation() -> dict[str, Any]:
    return {
        "versions": version_report(),
        "checks": [
            {"name": "python", "success": True},
            {"name": "package-assets", "success": True},
        ],
    }


def test_explicit_probes_do_not_discover_unselected_vault_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("unrequested operation")

    monkeypatch.setattr("knowlume.adapters.diagnostic_probes.FilesystemVault.discover", forbidden)
    monkeypatch.setattr("knowlume.adapters.diagnostic_probes._git_probe", lambda: None)
    monkeypatch.setattr("knowlume.adapters.diagnostic_probes._zotero_probe", forbidden)
    report, code = diagnostics.diagnostic_report(
        ("git", "git"),
        installation=installation,
        runner=LocalDiagnosticProbes(validate_vault=forbidden),
    )
    assert code == 0 and report["probes"] == ["git"]
    assert [c["status"] for c in report["checks"]] == [
        "passed",
        "passed",
        "skipped",
        "skipped",
        "passed",
        "skipped",
    ]
    assert not list(validator("doctor-result-v2.schema.json").iter_errors(report))


def test_vault_and_missing_sqlite_are_read_only(vault: Vault) -> None:
    before = snapshot(vault)
    directories = set(vault.root.rglob("*"))
    report, code = diagnostics.diagnostic_report(
        ("sqlite", "vault"),
        runner=LocalDiagnosticProbes(
            explicit_vault=vault.root, validate_vault=validate_vault_health
        ),
        installation=installation,
    )
    assert code == 5 and report["healthy"] is False
    assert report["checks"][2]["status"] == "passed"
    assert report["checks"][3]["code"] == "INDEX_NOT_FOUND"
    assert snapshot(vault) == before and set(vault.root.rglob("*")) == directories
    assert str(vault.root) not in json.dumps(report)


@pytest.mark.parametrize("state", ["fresh", "stale", "corrupt", "busy"])
def test_sqlite_probe_does_not_create_journals_or_repair(vault: Vault, state: str) -> None:
    projection = SQLiteProjection(
        ddl_reader=lambda _: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    projection.build(vault)
    database = projection.database_path(vault)
    if state == "stale":
        path = vault.root / "notes/ideas/idea.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
    elif state == "corrupt":
        database.write_bytes(b"not a database")
    elif state == "busy":
        Path(f"{database}-wal").write_bytes(b"writer state")
    before = snapshot(vault)
    report, code = diagnostics.diagnostic_report(
        ("sqlite",),
        runner=LocalDiagnosticProbes(
            explicit_vault=vault.root, validate_vault=validate_vault_health
        ),
        installation=installation,
    )
    assert (code == 0) is (state == "fresh")
    assert snapshot(vault) == before
    assert not Path(f"{database}-shm").exists()


@pytest.mark.parametrize("kind", ["transactions", "locks"])
def test_vault_probe_reports_without_recovery(vault: Vault, kind: str) -> None:
    (vault.path("state") / kind / "unfinished").write_text(
        "private recovery state", encoding="utf-8"
    )
    before = snapshot(vault)
    report, code = diagnostics.diagnostic_report(
        ("vault",),
        runner=LocalDiagnosticProbes(
            explicit_vault=vault.root, validate_vault=validate_vault_health
        ),
        installation=installation,
    )
    assert code == 4 and report["checks"][2]["status"] == "failed"
    assert snapshot(vault) == before and "private recovery state" not in json.dumps(report)


def test_probe_failures_are_aggregated_sanitized_and_prioritized() -> None:
    def absent() -> None:
        raise DomainError("GIT_CAPABILITY_UNAVAILABLE", "private credential path")

    def unsafe() -> None:
        raise DomainError("ZOTERO_ENDPOINT_UNSAFE", "http://private-secret")

    report, code = diagnostics.diagnostic_report(
        ("git", "zotero"),
        installation=installation,
        runner=StubProbes({"git": absent, "zotero": unsafe}),
    )
    assert code == 6
    assert [c["status"] for c in report["checks"]][-2:] == ["unavailable", "failed"]
    assert "private" not in json.dumps(report)


def test_unexpected_probe_error_is_sanitized() -> None:
    def broken() -> None:
        raise RuntimeError("secret-body")

    report, code = diagnostics.diagnostic_report(
        ("git",), installation=installation, runner=StubProbes({"git": broken})
    )
    assert code == 3 and "secret-body" not in json.dumps(report)


def test_git_probe_timeout_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("knowlume.adapters.diagnostic_probes.shutil.which", lambda _: "git")

    def timeout(*args: Any, **kwargs: Any) -> None:
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired("private executable", 5)

    monkeypatch.setattr("knowlume.adapters.diagnostic_probes.subprocess.run", timeout)
    with pytest.raises(DomainError) as caught:
        LocalDiagnosticProbes(validate_vault=validate_vault_health).probe("git")
    assert caught.value.code == "GIT_CAPABILITY_UNAVAILABLE"
    assert "private" not in str(caught.value)


def test_zotero_probe_only_uses_minimal_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    requested = []

    def request(self: ZoteroLocalApi, path: str, *, binary: bool = False) -> list[object]:
        requested.append((path, binary))
        return []

    monkeypatch.setattr(ZoteroLocalApi, "_request", request)
    ZoteroLocalApi().probe()
    assert requested == [("users/0/items?limit=1", False)]


@pytest.mark.parametrize(
    "response", [None, {}, [None], [{"data": "bad"}], [{"data": {}}, {"data": {}}]]
)
def test_zotero_probe_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch, response: object
) -> None:
    monkeypatch.setattr(ZoteroLocalApi, "_request", lambda *args, **kwargs: response)
    with pytest.raises(DomainError) as caught:
        ZoteroLocalApi().probe()
    assert caught.value.code == "ZOTERO_RESPONSE_INVALID"


@pytest.mark.parametrize("arguments", [["--probe", "unknown"], ["--probe"], ["--unknown"]])
def test_doctor_usage_errors_are_machine_readable(arguments: list[str]) -> None:
    result = CliRunner().invoke(app, ["doctor", *arguments, "--json"])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["errors"][0]["code"] == "DOCTOR_ARGUMENT_INVALID"


def test_doctor_cli_v1_compatibility_and_v2_failure_envelope(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("knowlume.doctor.validate_required_assets", lambda: [])
    old = CliRunner().invoke(app, ["doctor", "--json"])
    assert old.exit_code == 0 and json.loads(old.stdout)["data"]["report_version"] == 1
    assert not list(
        validator("doctor-result-v1.schema.json").iter_errors(json.loads(old.stdout)["data"])
    )
    new = CliRunner().invoke(
        app, ["--vault", str(vault.root), "doctor", "--probe", "sqlite", "--json"]
    )
    assert new.exit_code == 5
    envelope = json.loads(new.stdout)
    assert envelope["success"] is False and envelope["data"]["healthy"] is False
    assert not list(validator("cli-envelope-v1.schema.json").iter_errors(envelope))
    assert not list(validator("doctor-result-v2.schema.json").iter_errors(envelope["data"]))
