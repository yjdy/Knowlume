from __future__ import annotations

from collections.abc import Iterable

from typer import Typer
from typer.models import CommandInfo, TyperInfo
from typer.testing import CliRunner

from knowlume.cli import app, index_app, note_app, relation_app, source_app

runner = CliRunner()


def _command_names(commands: Iterable[CommandInfo]) -> set[str]:
    return {
        command.name or command.callback.__name__.replace("_", "-")
        for command in commands
        if command.callback is not None
    }


def _group_names(groups: Iterable[TyperInfo]) -> set[str]:
    return {group.name for group in groups if group.name is not None}


def _surface(typer: Typer) -> tuple[set[str], set[str]]:
    return _command_names(typer.registered_commands), _group_names(typer.registered_groups)


def test_registered_cli_inventory_through_phase3_is_exact() -> None:
    commands, groups = _surface(app)
    assert commands == {
        "add",
        "doctor",
        "context",
        "get",
        "grep",
        "init",
        "inbox",
        "lint",
        "migrate",
        "process",
        "scan",
        "search",
        "status",
        "update-check",
    }
    assert groups == {"index", "note", "relation", "source"}
    assert _surface(note_app) == ({"evolve", "new", "show"}, set())
    assert _surface(relation_app) == ({"add", "list", "remove"}, set())
    assert _surface(source_app) == ({"list", "open", "show", "sync"}, set())
    assert _surface(index_app) == ({"build", "rebuild", "status"}, set())


def test_every_phase1_command_has_help() -> None:
    commands = (
        ["--help"],
        ["init", "--help"],
        ["scan", "--help"],
        ["status", "--help"],
        ["lint", "--help"],
        ["migrate", "--help"],
        ["note", "new", "--help"],
        ["note", "show", "--help"],
        ["note", "evolve", "--help"],
        ["relation", "add", "--help"],
        ["relation", "remove", "--help"],
        ["relation", "list", "--help"],
        ["source", "list", "--help"],
        ["source", "show", "--help"],
        ["source", "open", "--help"],
        ["source", "sync", "--help"],
        ["inbox", "--help"],
        ["process", "--help"],
        ["doctor", "--help"],
        ["update-check", "--help"],
        ["grep", "--help"],
        ["get", "--help"],
        ["index", "build", "--help"],
        ["index", "rebuild", "--help"],
        ["index", "status", "--help"],
        ["search", "--help"],
        ["context", "--help"],
    )
    for command in commands:
        result = runner.invoke(app, command, color=False)
        assert result.exit_code == 0, command
        assert "Usage:" in result.stdout
