from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, NoReturn

import typer
from typer.core import TyperGroup

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.application.ai import AIService
from knowlume.application.indexing import IndexRefreshService
from knowlume.application.vault import VaultService
from knowlume.cli_errors import UsageError
from knowlume.domain.values import DomainError
from knowlume.envelope import error_envelope, render_json, success_envelope
from knowlume.ports.vault import Vault


def ai_exit_code(code: str) -> int:
    if code in {"AI_ARGUMENT_INVALID", "VAULT_ARGUMENT_CONFLICT"}:
        return 2
    if code in {"AI_CONTENT_UNSAFE", "VAULT_PATH_UNSAFE"}:
        return 6
    if code in {
        "AI_INPUT_CHANGED",
        "AI_PROMOTION_CONFLICT",
        "VAULT_WRITE_CONFLICT",
        "VAULT_LOCKED",
        "VAULT_RECOVERY_REQUIRED",
        "VAULT_RECOVERY_FAILED",
    }:
        return 4
    return 3


def _failure(command: str, error: DomainError, json_output: bool) -> NoReturn:
    code = ai_exit_code(error.code)
    if json_output:
        typer.echo(
            render_json(
                error_envelope(command, exit_code=code, code=error.code, message=str(error))
            )
        )
    else:
        typer.echo(f"{error.code}: {error}", err=True)
    raise typer.Exit(code)


class AIGroup(TyperGroup):
    """Keep Click's usage errors inside the machine envelope for AI commands."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        options = args[: args.index("--")] if "--" in args else args
        ctx.meta["ai_json"] = "--json" in options
        ctx.meta["ai_command"] = (
            f"ai {args[0]}" if args and args[0] in {"list", "review", "promote"} else "ai"
        )
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            if not ctx.meta["ai_json"]:
                raise
            _failure(
                ctx.meta["ai_command"],
                DomainError(
                    "AI_ARGUMENT_INVALID", "invalid AI command arguments; consult command help"
                ),
                True,
            )

    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except UsageError:
            if not ctx.meta.get("ai_json"):
                raise
            _failure(
                ctx.meta["ai_command"],
                DomainError(
                    "AI_ARGUMENT_INVALID", "invalid AI command arguments; consult command help"
                ),
                True,
            )


ai_app = typer.Typer(
    cls=AIGroup, help="Inspect, review and promote private AI Artifacts.", no_args_is_help=True
)


def _run(
    ctx: typer.Context,
    command: str,
    json_output: bool,
    operation: Callable[[Vault], dict[str, Any]],
) -> None:
    if ctx.meta.get("ai_json") and not json_output:
        _failure(
            command,
            DomainError("AI_ARGUMENT_INVALID", "--json cannot replace a required option value"),
            True,
        )
    try:
        vault = VaultService(FilesystemVault()).discover(explicit=ctx.find_root().obj.get("vault"))
        result = operation(vault)
        warnings = IndexRefreshService(SQLiteProjection()).after_mutation(
            vault, changed=result.get("changed", False)
        )
    except DomainError as error:
        _failure(command, error, json_output)
    except (OSError, UnicodeError):
        _failure(
            command,
            DomainError(
                "AI_OPERATION_FAILED", "AI operation could not read or write its local files"
            ),
            json_output,
        )
    envelope = success_envelope(command, result)
    envelope["warnings"] = [
        {
            "code": warning,
            "message": "Durable change succeeded; inspect and refresh the index explicitly.",
        }
        for warning in warnings
    ]
    if json_output:
        typer.echo(render_json(envelope))
    else:
        if command == "ai list":
            typer.echo(f"AI Artifacts: {result['total']}")
            for item in result["items"]:
                typer.echo(f"{item['object_id']}  {item['review_status']}  {item['title']}")
        elif command == "ai review":
            typer.echo(
                f"{result['artifact_id']}: {result['review_status']} ({result['reviewed_by']})"
            )
        else:
            typer.echo(
                f"{result['mode']}: {result['artifact_id']} -> "
                f"{result['note_id']}#{result['section_id']}"
            )
            typer.echo(result["preview"]["text"])
        for warning in warnings:
            typer.echo(f"WARNING {warning}", err=True)


@ai_app.command("list")
def list_artifacts(
    ctx: typer.Context,
    review_status: Annotated[str, typer.Option("--review-status")] = "unreviewed",
    artifact_type: Annotated[str, typer.Option("--type")] = "all",
    status: Annotated[str, typer.Option("--status")] = "active",
    limit: Annotated[int, typer.Option("--limit")] = 50,
    offset: Annotated[int, typer.Option("--offset")] = 0,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List local Artifact metadata without reading prompts or using an index."""
    _run(
        ctx,
        "ai list",
        json_output,
        lambda vault: AIService().list(
            vault,
            review_status=review_status,
            artifact_type=artifact_type,
            status=status,
            limit=limit,
            offset=offset,
        ),
    )
