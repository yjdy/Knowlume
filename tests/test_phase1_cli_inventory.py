from __future__ import annotations

from collections.abc import Iterable

from typer import Typer
from typer.models import CommandInfo, TyperInfo
from typer.testing import CliRunner

from knowlume.cli import app, note_app, relation_app

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


def test_registered_phase1_cli_inventory_is_exact() -> None:
    commands, groups = _surface(app)
    assert commands == {
        "doctor",
        "init",
        "lint",
        "migrate",
        "scan",
        "status",
        "update-check",
    }
    assert groups == {"note", "relation"}
    assert _surface(note_app) == ({"evolve", "new", "show"}, set())
    assert _surface(relation_app) == ({"add", "list", "remove"}, set())


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
        ["doctor", "--help"],
        ["update-check", "--help"],
    )
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, command
        assert "--help" in result.stdout
