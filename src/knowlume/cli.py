from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.adapters.git_remote import GitRemoteResolver
from knowlume.adapters.zotero_local import ZoteroLocalApi
from knowlume.application.capture import UnifiedCaptureService
from knowlume.application.migration import MigrationService
from knowlume.application.notes import NoteService
from knowlume.application.relations import ListedRelation, RelationService
from knowlume.application.scanning import Finding, changed_paths, scan_vault
from knowlume.application.sources import SourceService
from knowlume.application.vault import VaultService
from knowlume.doctor import doctor_report
from knowlume.domain.values import DomainError
from knowlume.envelope import error_envelope, render_json, success_envelope
from knowlume.ports.vault import Vault
from knowlume.resources import read_asset_text
from knowlume.updates import UpdateCheckError, check_for_updates
from knowlume.versioning import format_version_report

app = typer.Typer(
    add_completion=False,
    help="Local-first personal knowledge tools.",
    no_args_is_help=True,
)
note_app = typer.Typer(help="Create, show, and evolve Notes.", no_args_is_help=True)
relation_app = typer.Typer(help="Add, remove, and list durable relations.", no_args_is_help=True)
source_app = typer.Typer(help="List, show, open, and synchronize Sources.", no_args_is_help=True)
app.add_typer(note_app, name="note")
app.add_typer(relation_app, name="relation")
app.add_typer(source_app, name="source")


def _configure_cli_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(format_version_report())
        raise typer.Exit(0)


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show package and contract versions.",
        ),
    ] = False,
    vault: Annotated[
        Path | None,
        typer.Option("--vault", help="Use an explicit Knowlume Vault root."),
    ] = None,
) -> None:
    """Knowlume command line interface."""
    _configure_cli_streams()
    ctx.ensure_object(dict)
    ctx.obj["vault"] = vault


def _exit_with_domain_error(error: DomainError) -> NoReturn:
    exit_code = 3
    if error.code == "VAULT_ARGUMENT_CONFLICT":
        exit_code = 2
    elif error.code in {
        "VAULT_WRITE_CONFLICT",
        "VAULT_LOCKED",
        "VAULT_RECOVERY_REQUIRED",
        "VAULT_RECOVERY_FAILED",
        "PAPER_ATTACHMENT_CHANGED",
        "SOURCE_SYNC_LOCAL_MODIFIED",
        "SOURCE_SYNC_BASELINE_REQUIRED",
    }:
        exit_code = 4
    elif error.code == "VAULT_PATH_UNSAFE":
        exit_code = 6
    elif error.code == "CHANGED_FILES_UNAVAILABLE" or error.code.startswith("ZOTERO_"):
        exit_code = 5
    typer.echo(f"{error.code}: {error}", err=True)
    raise typer.Exit(exit_code)


@app.command("init")
def init_vault(
    ctx: typer.Context, path: Annotated[Path, typer.Argument(help="Vault directory")]
) -> None:
    """Initialize an independent Contract v2 Vault."""

    if ctx.obj.get("vault") is not None:
        _exit_with_domain_error(
            DomainError("VAULT_ARGUMENT_CONFLICT", "--vault cannot be combined with init PATH")
        )
    try:
        config_text = read_asset_text("templates/config/v1/knowlume.toml")
        vault = VaultService(FilesystemVault()).initialize(path, config_text)
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(f"Initialized Knowlume Vault: {vault.root}")


def _resolved_vault(ctx: typer.Context) -> Vault:
    try:
        return VaultService(FilesystemVault()).discover(explicit=ctx.obj.get("vault"))
    except DomainError as error:
        _exit_with_domain_error(error)


def _render_finding(finding: Finding) -> str:
    location = ":".join(
        value for value in (finding.path, finding.object_id, finding.section_id) if value
    )
    prefix = f"{finding.severity.upper()} {finding.code}"
    return f"{prefix} {location}: {finding.message}" if location else f"{prefix}: {finding.message}"


@app.command("scan")
def scan_command(ctx: typer.Context) -> None:
    """Parse and validate all durable Contract v2 Vault files."""

    result = scan_vault(_resolved_vault(ctx))
    typer.echo(
        f"Scanned {result.files_scanned} durable files; "
        f"{len(result.objects)} objects; {len(result.relation_shards)} relation shards."
    )
    for finding in result.findings:
        typer.echo(_render_finding(finding), err=True)
    if not result.healthy:
        raise typer.Exit(3)


@app.command("status")
def status_command(ctx: typer.Context) -> None:
    """Summarize Vault objects and scanner health."""

    result = scan_vault(_resolved_vault(ctx))
    counts = result.object_counts()
    health = "healthy" if result.healthy else "unhealthy"
    typer.echo(
        f"Vault is {health}: {counts['source']} sources, {counts['note']} notes, "
        f"{counts['snippet']} snippets, {counts['ai_artifact']} AI artifacts, "
        f"{len(result.findings)} findings."
    )


@app.command("lint")
def lint_command(
    ctx: typer.Context,
    strict: Annotated[
        bool, typer.Option("--strict", help="Fail on warnings as well as errors.")
    ] = False,
    changed: Annotated[
        bool,
        typer.Option("--changed", help="Display findings for Git-changed files only."),
    ] = False,
) -> None:
    """Report Contract, reference, provenance, relation, and safety findings."""

    if strict and changed:
        _exit_with_domain_error(
            DomainError("VAULT_ARGUMENT_CONFLICT", "--strict and --changed are mutually exclusive")
        )
    vault = _resolved_vault(ctx)
    result = scan_vault(vault)
    findings = result.findings
    if changed:
        try:
            selected = changed_paths(vault)
        except DomainError as error:
            _exit_with_domain_error(error)
        findings = tuple(finding for finding in findings if finding.path in selected)
    for finding in findings:
        typer.echo(_render_finding(finding))
    typer.echo(f"{len(findings)} finding(s).")
    if any(
        finding.severity == "error" or (strict and finding.severity == "warning")
        for finding in findings
    ):
        raise typer.Exit(3)


def _note_service() -> NoteService:
    return NoteService(filesystem=FilesystemVault(), template_reader=read_asset_text)


def _relation_service() -> RelationService:
    return RelationService(filesystem=FilesystemVault())


def _migration_service() -> MigrationService:
    return MigrationService(
        config_reader=lambda: read_asset_text("templates/config/v1/knowlume.toml")
    )


def _source_service() -> SourceService:
    return SourceService(filesystem=FilesystemVault(), zotero=ZoteroLocalApi())


def _capture_service() -> UnifiedCaptureService:
    return UnifiedCaptureService(
        filesystem=FilesystemVault(),
        zotero=ZoteroLocalApi(),
        repositories=GitRemoteResolver(),
    )


def _source_exit_code(error: DomainError) -> int:
    if error.code in {"ADD_INPUT_INVALID", "VAULT_ARGUMENT_CONFLICT"}:
        return 2
    if error.code in {
        "VAULT_WRITE_CONFLICT",
        "PAPER_ATTACHMENT_CHANGED",
        "SOURCE_SYNC_LOCAL_MODIFIED",
        "SOURCE_SYNC_BASELINE_REQUIRED",
    }:
        return 4
    if error.code.startswith("ZOTERO_"):
        return 5
    if error.code == "VAULT_PATH_UNSAFE":
        return 6
    return 3


def _exit_source_error(error: DomainError, *, command: str, json_output: bool) -> NoReturn:
    exit_code = _source_exit_code(error)
    if json_output:
        typer.echo(
            render_json(
                error_envelope(
                    command,
                    exit_code=exit_code,
                    code=error.code,
                    message=str(error),
                )
            )
        )
        raise typer.Exit(exit_code)
    _exit_with_domain_error(error)


def _success_with_warnings(command: str, data: object, warnings: tuple[str, ...]) -> str:
    envelope = success_envelope(command, data)
    envelope["warnings"] = [
        {"code": code, "message": code.replace("_", " ").title()} for code in warnings
    ]
    return render_json(envelope)


def _add_exit_code(code: str) -> int:
    return {
        "ADD_INPUT_INVALID": 2,
        "ADD_TYPE_AMBIGUOUS": 3,
        "ADD_IDENTITY_CONFLICT": 3,
        "ADD_WRITE_CONFLICT": 4,
        "ADD_METADATA_UNAVAILABLE": 5,
    }.get(code, 3)


def _exit_add_error(error: DomainError, *, json_output: bool) -> NoReturn:
    exit_code = _add_exit_code(error.code)
    if json_output:
        typer.echo(
            render_json(
                error_envelope(
                    "add",
                    exit_code=exit_code,
                    code=error.code,
                    message=str(error),
                )
            )
        )
    else:
        typer.echo(f"{error.code}: {error}", err=True)
    raise typer.Exit(exit_code)


@app.command("add")
def add_command(
    ctx: typer.Context,
    value: Annotated[str, typer.Argument(help="DOI, arXiv, ISBN, Web URL, or repository URL")],
    requested_type: Annotated[
        str | None,
        typer.Option("--type", help="Select paper, web, book, or repo recognition."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Capture a Paper, Web page, Book, or repository as a private Source."""

    try:
        result = _capture_service().add(_resolved_vault(ctx), value, requested_type)
    except DomainError as error:
        _exit_add_error(error, json_output=json_output)
    if json_output:
        typer.echo(_success_with_warnings("add", result.data(), result.warnings))
        return
    action = "Created" if result.created else "Found existing"
    typer.echo(
        f"{action} {result.detected_type} Source {result.source_id}: "
        f"{result.canonical_identity}"
    )
    for warning in result.warnings:
        typer.echo(f"WARNING {warning}", err=True)


def _render_relation(relation: ListedRelation) -> str:
    target = str(relation.to_id)
    if relation.to_section_id:
        target = f"{target}#{relation.to_section_id}"
    return f"{relation.direction} {relation.relation_type.value} {relation.from_id} -> {target}"


@note_app.command("new")
def note_new(
    ctx: typer.Context,
    note_type: Annotated[
        str,
        typer.Option("--type", help="Note type: idea, literature, concept, or synthesis."),
    ],
    source: Annotated[
        str | None,
        typer.Option("--source", help="Existing Source ID required for a Literature Note."),
    ] = None,
) -> None:
    """Create a private Note from a bundled Contract v2 template."""

    try:
        object_id = _note_service().create(_resolved_vault(ctx), note_type, source_id_value=source)
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(str(object_id))


@note_app.command("show")
def note_show(
    ctx: typer.Context, object_id: Annotated[str, typer.Argument(help="Note ID")]
) -> None:
    """Display a normalized Note by stable ID."""

    try:
        rendered = _note_service().show(_resolved_vault(ctx), object_id)
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(rendered, nl=False)


@note_app.command("evolve")
def note_evolve(
    ctx: typer.Context,
    object_id: Annotated[str, typer.Argument(help="Idea Note ID")],
    target: Annotated[str, typer.Option("--to", help="Evolution target; only concept.")],
) -> None:
    """Evolve an Idea to Concept without changing durable identities."""

    try:
        evolved_id = _note_service().evolve(_resolved_vault(ctx), object_id, target)
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(str(evolved_id))


@relation_app.command("add")
def relation_add(
    ctx: typer.Context,
    from_id: Annotated[str, typer.Argument(help="Source object ID")],
    to_id: Annotated[str, typer.Argument(help="Target object ID")],
    relation_type: Annotated[str, typer.Option("--type", help="Relation type")],
    section: Annotated[
        str | None,
        typer.Option("--section", help="Stable section ID on the stored target object."),
    ] = None,
) -> None:
    """Add one canonical relation to its owning shard."""

    try:
        relation = _relation_service().add(
            _resolved_vault(ctx),
            from_id,
            to_id,
            relation_type,
            to_section_value=section,
        )
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(_render_relation(relation))


@relation_app.command("remove")
def relation_remove(
    ctx: typer.Context,
    from_id: Annotated[str, typer.Argument(help="Source object ID")],
    to_id: Annotated[str, typer.Argument(help="Target object ID")],
    relation_type: Annotated[str, typer.Option("--type", help="Relation type")],
    section: Annotated[
        str | None,
        typer.Option("--section", help="Stable section ID on the stored target object."),
    ] = None,
) -> None:
    """Remove exactly one relation by its canonical key."""

    try:
        relation = _relation_service().remove(
            _resolved_vault(ctx),
            from_id,
            to_id,
            relation_type,
            to_section_value=section,
        )
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(_render_relation(relation))


@relation_app.command("list")
def relation_list(
    ctx: typer.Context,
    object_id: Annotated[str, typer.Argument(help="Object ID")],
) -> None:
    """List stored outgoing and scanner-derived incoming relations."""

    try:
        relations = _relation_service().list(_resolved_vault(ctx), object_id)
    except DomainError as error:
        _exit_with_domain_error(error)
    for relation in relations:
        typer.echo(_render_relation(relation))
    typer.echo(f"{len(relations)} relation(s).")


@source_app.command("list")
def source_list(
    ctx: typer.Context,
    source_type: Annotated[
        str | None, typer.Option("--type", help="Filter by paper, web, book, or oss.")
    ] = None,
    stage: Annotated[str | None, typer.Option("--stage", help="Filter by workflow stage.")] = None,
    status: Annotated[str | None, typer.Option("--status", help="Filter by record status.")] = None,
    visibility: Annotated[
        str | None, typer.Option("--visibility", help="Filter by visibility.")
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """List durable Sources using the scanner rather than SQLite."""

    try:
        result = _source_service().list(
            _resolved_vault(ctx),
            source_type=source_type,
            workflow_stage=stage,
            record_status=status,
            visibility=visibility,
        )
    except DomainError as error:
        _exit_source_error(error, command="source list", json_output=json_output)
    if json_output:
        typer.echo(render_json(success_envelope("source list", result)))
        return
    for source in result["sources"]:
        typer.echo(
            f"{source['source_id']} {source['source_type']} {source['workflow_stage']} "
            f"{source['title']}"
        )
    typer.echo(f"{result['count']} source(s).")


@source_app.command("show")
def source_show(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source ID")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Display a normalized Source without probing its adapter."""

    service = _source_service()
    try:
        if json_output:
            typer.echo(
                render_json(
                    success_envelope("source show", service.show(_resolved_vault(ctx), source_id))
                )
            )
        else:
            typer.echo(service.rendered(_resolved_vault(ctx), source_id), nl=False)
    except DomainError as error:
        _exit_source_error(error, command="source show", json_output=json_output)


@source_app.command("open")
def source_open(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source ID")],
) -> None:
    """Recover, verify, and open the recorded primary PDF."""

    try:
        _source_service().open(_resolved_vault(ctx), source_id)
    except DomainError as error:
        _exit_source_error(error, command="source open", json_output=False)
    typer.echo(f"Opened primary attachment for {source_id}.")


@source_app.command("sync")
def source_sync(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source ID")],
    adopt_remote: Annotated[
        bool,
        typer.Option("--adopt-remote", help="Explicitly adopt remote managed fields."),
    ] = False,
    accept_attachment_change: Annotated[
        bool,
        typer.Option(
            "--accept-attachment-change",
            help="Accept changed PDF bytes and require locator review.",
        ),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Synchronize Zotero-managed fields with durable conflict checks."""

    try:
        result = _source_service().sync(
            _resolved_vault(ctx),
            source_id,
            adopt_remote=adopt_remote,
            accept_attachment_change=accept_attachment_change,
        )
    except DomainError as error:
        _exit_source_error(error, command="source sync", json_output=json_output)
    if json_output:
        typer.echo(_success_with_warnings("source sync", result.data(), result.warnings))
        return
    action = "updated" if result.changed else "unchanged"
    typer.echo(f"Source {source_id} is {action}.")
    for warning in result.warnings:
        typer.echo(f"WARNING {warning}", err=True)


@app.command("inbox")
def inbox_command(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """List Sources waiting in the inbox workflow stage."""

    try:
        result = _source_service().list(_resolved_vault(ctx), inbox=True)
    except DomainError as error:
        _exit_source_error(error, command="inbox", json_output=json_output)
    if json_output:
        typer.echo(render_json(success_envelope("inbox", result)))
        return
    for source in result["sources"]:
        typer.echo(f"{source['source_id']} {source['source_type']} {source['title']}")
    typer.echo(f"{result['count']} inbox source(s).")


@app.command("process")
def process_command(
    ctx: typer.Context,
    source_id: Annotated[str, typer.Argument(help="Source ID")],
    target: Annotated[
        str, typer.Option("--to", help="Adjacent target: reading, processed, or integrated.")
    ],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Advance a Source by one explicit workflow stage."""

    try:
        result = _source_service().process(_resolved_vault(ctx), source_id, target)
    except DomainError as error:
        _exit_source_error(error, command="process", json_output=json_output)
    if json_output:
        typer.echo(render_json(success_envelope("process", result.data())))
        return
    typer.echo(
        f"{source_id}: {result.previous_stage.value} -> {result.current_stage.value}"
        f" ({'changed' if result.changed else 'unchanged'})"
    )


@app.command("migrate")
def migrate_command(
    ctx: typer.Context,
    from_contract: Annotated[int, typer.Option("--from", help="Source Contract version")],
    to_contract: Annotated[int, typer.Option("--to", help="Target Contract version")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without durable writes; this is the default."),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Apply only when the report has no unresolved findings."),
    ] = False,
) -> None:
    """Preview or apply the explicit Contract v1-to-v2 migration."""

    if (from_contract, to_contract) != (1, 2) or (dry_run and apply):
        _exit_with_domain_error(
            DomainError(
                "VAULT_ARGUMENT_CONFLICT",
                "only --from 1 --to 2 is supported; choose at most one mode",
            )
        )
    root = ctx.obj.get("vault") or Path.cwd()
    try:
        report = _migration_service().run(root, apply=apply)
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(json.dumps(report.data(), ensure_ascii=False, indent=2))
    if apply and not report.apply_allowed:
        raise typer.Exit(3)


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
