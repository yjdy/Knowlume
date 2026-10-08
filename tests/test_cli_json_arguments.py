from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_phase5_contracts import validator
from typer.main import get_command
from typer.testing import CliRunner

import knowlume.cli as cli
from knowlume.adapters.filesystem import FilesystemVault
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.domain.values import DomainError

ROOT = Path(__file__).resolve().parents[1]
RUNNER = CliRunner()
JSON_COMMANDS = (
    "add",
    "inbox",
    "process",
    "source list",
    "source show",
    "source sync",
    "grep",
    "get",
    "search",
    "context",
    "index build",
    "index rebuild",
    "index status",
    "ai list",
    "ai review",
    "ai promote",
    "doctor",
    "update-check",
)


def assert_failure(result: Any, command: str) -> dict[str, Any]:
    assert result.exit_code == 2, (result.stdout, result.stderr, result.exception)
    assert result.stderr == ""
    document: dict[str, Any] = json.loads(result.stdout)
    assert not list(validator("cli-envelope-v1.schema.json").iter_errors(document))
    code = (
        "AI_ARGUMENT_INVALID"
        if command.startswith("ai")
        else "DOCTOR_ARGUMENT_INVALID"
        if command == "doctor"
        else "CLI_ARGUMENT_INVALID"
    )
    assert document["command"] == command
    assert document["interface_version"] == 1
    assert document["success"] is False and document["exit_code"] == 2
    assert document["data"] is None and document["warnings"] == []
    assert len(document["errors"]) == 1 and document["errors"][0]["code"] == code
    messages = {
        "CLI_ARGUMENT_INVALID": {"invalid command arguments; consult command help"},
        "DOCTOR_ARGUMENT_INVALID": {"invalid doctor arguments; consult command help"},
        "AI_ARGUMENT_INVALID": {
            "invalid AI command arguments; consult command help",
            "--json cannot replace a required option value",
        },
    }
    assert document["errors"][0]["message"] in messages[code]
    return document


@pytest.fixture
def no_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("argument failure reached a business operation")

    for name in (
        "_resolved_vault",
        "_capture_service",
        "_source_service",
        "_projection",
        "_query_service",
        "check_for_updates",
        "doctor_report",
    ):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr("knowlume.application.vault.VaultService.discover", forbidden)
    monkeypatch.setattr(
        "knowlume.application.indexing.IndexRefreshService.after_mutation", forbidden
    )
    monkeypatch.setattr("knowlume.application.diagnostics.diagnostic_report", forbidden)


def test_json_command_inventory_is_exhaustive() -> None:
    def walk(command: Any, path: tuple[str, ...] = ()) -> Iterator[str]:
        if hasattr(command, "commands"):
            for name, child in command.commands.items():
                yield from walk(child, (*path, name))
        elif any("--json" in getattr(param, "opts", ()) for param in command.params):
            yield " ".join(path)

    assert set(walk(get_command(cli.app))) == set(JSON_COMMANDS)


@pytest.mark.parametrize("command", JSON_COMMANDS)
def test_every_json_command_rejects_unknown_options_before_business(
    command: str,
    no_operations: None,
) -> None:
    secret = "synthetic-private-input"
    result = RUNNER.invoke(cli.app, [*command.split(), f"--{secret}", "--json"])
    assert_failure(result, command)
    assert secret not in result.output


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("context", ["knowledge"]),
        ("get", []),
        ("source show", []),
        ("source sync", []),
        ("add", []),
        ("process", ["synthetic-id"]),
        ("search", ["knowledge", "--limit", "private-number"]),
        ("search", ["knowledge", "--limit"]),
        ("context", ["knowledge", "--scope"]),
        ("index status", ["private-extra-argument"]),
    ],
)
def test_argument_error_shapes(
    command: str,
    arguments: list[str],
    no_operations: None,
) -> None:
    result = RUNNER.invoke(cli.app, [*command.split(), *arguments, "--json"])
    assert_failure(result, command)
    assert "private-number" not in result.output and "private-extra-argument" not in result.output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--json", "knowledge"],
        ["knowledge", "--json"],
        ["knowledge", "--scope", "--json"],
        ["knowledge", "--scope", "--json", "--json"],
    ],
)
def test_context_json_intent_and_consumed_flags(arguments: list[str], no_operations: None) -> None:
    assert_failure(RUNNER.invoke(cli.app, ["context", *arguments]), "context")


@pytest.mark.parametrize("command", JSON_COMMANDS)
def test_help_and_human_usage_remain_compatible(command: str, no_operations: None) -> None:
    help_result = RUNNER.invoke(cli.app, [*command.split(), "--help", "--json"])
    assert help_result.exit_code == 0 and "Usage:" in help_result.stdout
    human = RUNNER.invoke(cli.app, [*command.split(), "--unknown"])
    assert human.exit_code == 2 and human.stdout == "" and "Usage:" in human.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        ["context", "knowledge", "--", "--json"],
        ["context", "--scope=--json"],
        ["--unknown", "context", "--json"],
        ["--json", "context", "knowledge"],
        ["source", "unknown", "--json"],
        ["index", "--json"],
        ["note", "new", "--json"],
        ["source", "open", "--json"],
    ],
)
def test_no_new_json_scope(arguments: list[str], no_operations: None) -> None:
    result = RUNNER.invoke(cli.app, arguments)
    assert result.exit_code == 2 and result.stdout == "" and "Usage:" in result.stderr


def test_ai_unknown_group_command_keeps_existing_json_behavior(no_operations: None) -> None:
    assert_failure(RUNNER.invoke(cli.app, ["ai", "unknown", "--json"]), "ai")


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("search", ["knowledge", "--tag", "--json", "--json"]),
        ("doctor", ["--probe", "--json", "--json"]),
        (
            "ai review",
            [
                "synthetic-id",
                "--decision",
                "accepted",
                "--expect-checksum",
                "hash",
                "--reviewer",
                "--json",
                "--json",
            ],
        ),
    ],
)
def test_second_json_flag_does_not_allow_consumed_value(
    command: str,
    arguments: list[str],
    no_operations: None,
) -> None:
    document = assert_failure(RUNNER.invoke(cli.app, [*command.split(), *arguments]), command)
    if command.startswith("ai"):
        assert document["errors"][0]["message"] == "--json cannot replace a required option value"


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("search", ["knowledge", "--tag", "--", "--limit", "private-number", "--json"]),
        ("source list", ["--type", "--", "--synthetic-private-input", "--json"]),
        ("search", ["knowledge", "--tag", "--", "--tag", "--json", "--json"]),
        ("doctor", ["--probe", "--", "--probe", "--json", "--json"]),
        (
            "ai review",
            [
                "synthetic-id",
                "--reviewer",
                "--",
                "--reviewer",
                "--json",
                "--json",
                "--decision",
                "accepted",
                "--expect-checksum",
                "hash",
            ],
        ),
    ],
)
def test_option_value_double_dash_does_not_end_json_intent(
    command: str,
    arguments: list[str],
    no_operations: None,
) -> None:
    result = RUNNER.invoke(cli.app, [*command.split(), *arguments])
    assert_failure(result, command)
    assert "private-number" not in result.output
    assert "synthetic-private-input" not in result.output


def test_actual_terminator_after_double_dash_option_value_keeps_human_usage(
    no_operations: None,
) -> None:
    result = RUNNER.invoke(cli.app, ["search", "knowledge", "--tag", "--", "--", "--json"])
    assert result.exit_code == 2 and result.stdout == "" and "Usage:" in result.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        ["knowledge", "--tag=--json", "--json"],
        ["knowledge", "--tag", "--", "--json"],
        ["knowledge", "--tag", "--scope", "--json"],
        ["--json", "--", "--json"],
    ],
)
def test_json_literals_and_option_like_values_remain_valid(
    tmp_path: Path,
    arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    monkeypatch.setattr(cli, "_projection", lambda: projection)
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "vault", (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
    )
    prefix = ["--vault", str(vault.root)]
    assert RUNNER.invoke(cli.app, [*prefix, "index", "build", "--json"]).exit_code == 0
    result = RUNNER.invoke(cli.app, [*prefix, "search", *arguments])
    assert result.exit_code == 0, result.output
    assert result.stderr == "" and json.loads(result.stdout)["success"] is True
    human = RUNNER.invoke(cli.app, [*prefix, "search", "--", "--json"])
    assert human.exit_code == 0 and human.stdout == "0 hit(s).\n"


@pytest.mark.parametrize("internal", [False, True])
def test_business_and_internal_errors_are_not_reclassified(
    monkeypatch: pytest.MonkeyPatch,
    internal: bool,
) -> None:
    failure = (
        RuntimeError("synthetic failure")
        if internal
        else DomainError("SEARCH_QUERY_INVALID", "invalid query")
    )

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(cli, "_resolved_vault", lambda ctx: None)
    monkeypatch.setattr(cli, "grep_vault", fail)
    result = RUNNER.invoke(cli.app, ["grep", "knowledge", "--json"])
    if internal:
        assert result.exception is failure and result.stdout == ""
    else:
        assert result.exit_code == 2 and result.stderr == ""
        assert json.loads(result.stdout)["errors"][0]["code"] == "SEARCH_QUERY_INVALID"


@pytest.mark.parametrize(
    "command",
    ["add", "source sync", "process", "index build", "index rebuild", "ai review", "ai promote"],
)
def test_failed_mutations_leave_vault_untouched(tmp_path: Path, command: str) -> None:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "vault", (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
    )

    def snapshot() -> dict[str, bytes | None]:
        return {
            p.relative_to(vault.root).as_posix(): p.read_bytes() if p.is_file() else None
            for p in vault.root.rglob("*")
        }

    before = snapshot()
    result = RUNNER.invoke(
        cli.app, ["--vault", str(vault.root), *command.split(), "--unknown", "--json"]
    )
    assert_failure(result, command)
    assert snapshot() == before
