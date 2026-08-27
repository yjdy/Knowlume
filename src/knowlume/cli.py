from __future__ import annotations

from typing import Annotated, NoReturn

import typer

from knowlume.doctor import doctor_report
from knowlume.envelope import error_envelope, render_json, success_envelope
from knowlume.updates import UpdateCheckError, check_for_updates
from knowlume.versioning import format_version_report

app = typer.Typer(
    add_completion=False,
    help="Local-first personal knowledge tools.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(format_version_report())
        raise typer.Exit(0)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show package and contract versions.",
        ),
    ] = False,
) -> None:
    """Knowlume command line interface."""


def _exit_with_update_error(error: UpdateCheckError, json_output: bool) -> NoReturn:
    message = str(error)
    if json_output:
        typer.echo(
            render_json(
                error_envelope(
                    "update-check",
                    exit_code=5,
                    code="UPDATE_CHECK_UNAVAILABLE",
                    message=message,
                )
            )
        )
    else:
        typer.echo(f"Update check failed: {message}", err=True)
    raise typer.Exit(5)


@app.command("update-check")
def update_check(
    include_prereleases: Annotated[
        bool,
        typer.Option("--pre", help="Include prerelease versions."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit one machine-readable JSON document."),
    ] = False,
) -> None:
    """Explicitly check PyPI metadata for a newer package version."""

    try:
        result = check_for_updates(include_prereleases=include_prereleases)
    except UpdateCheckError as error:
        _exit_with_update_error(error, json_output)
    if json_output:
        typer.echo(render_json(success_envelope("update-check", result)))
        return
    if result["update_available"]:
        typer.echo(f"Knowlume {result['latest_version']} is available: {result['release_url']}")
    else:
        typer.echo(f"Knowlume {result['current_version']} is up to date.")


@app.command()
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit one machine-readable JSON document."),
    ] = False,
) -> None:
    """Check the installed runtime and bundled release assets."""

    report = doctor_report()
    if json_output:
        typer.echo(render_json(success_envelope("doctor", report)))
        return
    status = "healthy" if report["healthy"] else "unhealthy"
    typer.echo(f"Knowlume installation is {status}.")
    for check in report["checks"]:
        marker = "OK" if check["success"] else "ERROR"
        typer.echo(f"[{marker}] {check['name']}: {check['detail']}")
