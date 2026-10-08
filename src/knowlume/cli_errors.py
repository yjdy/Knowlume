from __future__ import annotations

from typing import Any, NoReturn

import typer
from typer.core import TyperCommand

from knowlume.envelope import error_envelope, render_json

__all__ = [
    "AICommand",
    "DoctorCommand",
    "JSONCommand",
    "UsageError",
    "json_requested",
    "usage_error",
]

try:
    from typer._click.exceptions import UsageError
except ImportError:  # Typer before its vendored command runtime.
    from click.exceptions import UsageError  # type: ignore[assignment]


def _option_tokens(args: list[str]) -> list[str]:
    return args[: args.index("--")] if "--" in args else args


def json_requested(args: list[str]) -> bool:
    return "--json" in _option_tokens(args)


def usage_error(command: str, *, code: str, message: str) -> NoReturn:
    typer.echo(render_json(error_envelope(command, exit_code=2, code=code, message=message)))
    raise typer.Exit(2) from None


def _command_path(ctx: Any) -> str:
    names = []
    while ctx.parent is not None:
        names.append(ctx.command.name)
        ctx = ctx.parent
    return " ".join(reversed(names))


class JSONCommand(TyperCommand):
    """Handle JSON usage failures before invoking any command's business logic."""

    argument_code = "CLI_ARGUMENT_INVALID"
    argument_message = "invalid command arguments; consult command help"
    consumed_message = argument_message

    def _consumed_json(self, ctx: Any, args: list[str]) -> bool:
        # Use declared option arity to distinguish `--tag --json` from the literal
        # value in `--tag=--json`. Skip values, so `--tag --scope --json` is valid.
        options = {
            name: param
            for param in self.get_params(ctx)
            for name in param.opts
            if name.startswith("-")
        }
        tokens = _option_tokens(args)
        index = 0
        while index < len(tokens):
            name, equals, _value = tokens[index].partition("=")
            option = options.get(name)
            if option is not None and not getattr(option, "is_flag", False) and not equals:
                values = tokens[index + 1 : index + 1 + option.nargs]
                if "--json" in values:
                    return True
                index += option.nargs
            index += 1
        return False

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        requested = json_requested(args)
        consumed = self._consumed_json(ctx, args) if requested else False
        try:
            remaining = super().parse_args(ctx, args)
        except UsageError:
            if not requested:
                raise
            usage_error(_command_path(ctx), code=self.argument_code, message=self.argument_message)
        # Eager --help has already exited. Reject swallowed flags even if a second
        # --json set json_output, without resolving a Vault or running a callback.
        if requested and (consumed or not ctx.params.get("json_output")):
            usage_error(_command_path(ctx), code=self.argument_code, message=self.consumed_message)
        return remaining


class DoctorCommand(JSONCommand):
    argument_code = "DOCTOR_ARGUMENT_INVALID"
    argument_message = "invalid doctor arguments; consult command help"
    consumed_message = argument_message


class AICommand(JSONCommand):
    argument_code = "AI_ARGUMENT_INVALID"
    argument_message = "invalid AI command arguments; consult command help"
    consumed_message = "--json cannot replace a required option value"
