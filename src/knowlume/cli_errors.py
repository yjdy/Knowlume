from __future__ import annotations

from typing import Any

import typer
from typer.core import TyperCommand

from knowlume.envelope import error_envelope, render_json

__all__ = ["DoctorCommand", "UsageError"]

try:
    from typer._click.exceptions import UsageError
except ImportError:  # Typer before its vendored command runtime.
    from click.exceptions import UsageError  # type: ignore[assignment]


class DoctorCommand(TyperCommand):
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        options = args[: args.index("--")] if "--" in args else args
        ctx.meta["doctor_json_requested"] = "--json" in options
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            if "--json" not in options:
                raise
            typer.echo(
                render_json(
                    error_envelope(
                        "doctor",
                        exit_code=2,
                        code="DOCTOR_ARGUMENT_INVALID",
                        message="invalid doctor arguments; consult command help",
                    )
                )
            )
            raise typer.Exit(2) from None
