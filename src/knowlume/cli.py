from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn, cast

import typer

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.adapters.git_remote import GitRemoteResolver
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.adapters.zotero_local import ZoteroLocalApi
from knowlume.application.capture import UnifiedCaptureService
from knowlume.application.indexing import IndexRefreshService
from knowlume.application.migration import MigrationService
from knowlume.application.notes import NoteService
from knowlume.application.query import QueryService, get_object, grep_vault
from knowlume.application.relations import ListedRelation, RelationService
from knowlume.application.scanning import Finding, changed_paths, scan_vault
from knowlume.application.sources import SourceService
from knowlume.application.vault import VaultService
from knowlume.doctor import doctor_report
from knowlume.domain.search import ContextScope, SearchFilters
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
index_app = typer.Typer(help="Build and inspect the disposable search index.", no_args_is_help=True)
app.add_typer(note_app, name="note")
app.add_typer(relation_app, name="relation")
app.add_typer(source_app, name="source")
app.add_typer(index_app, name="index")


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
    elif error.code in {"INDEX_NOT_FOUND"}:
        exit_code = 5
    elif error.code in {"INDEX_SOURCE_CHANGED", "INDEX_BUSY"}:
        exit_code = 4
    elif error.code == "SEARCH_QUERY_INVALID":
        exit_code = 2
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


def _projection() -> SQLiteProjection:
    return SQLiteProjection()


def _query_service() -> QueryService:
    return QueryService(_projection())


def _exit_web_error(error: DomainError) -> NoReturn:
    exit_code = 2 if error.code == "WEB_ARGUMENT_INVALID" else 5
    typer.echo(f"{error.code}: {error}", err=True)
    raise typer.Exit(exit_code)


def _refresh_warning(vault: Vault, *, changed: bool = True) -> tuple[str, ...]:
    if not changed or not isinstance(vault, Vault):
        return ()
    return IndexRefreshService(_projection()).after_mutation(vault, changed=changed)


def _render_warnings(warnings: tuple[str, ...]) -> None:
    for warning in warnings:
        typer.echo(f"WARNING {warning}", err=True)


def _phase3_exit_code(code: str) -> int:
    return {
        "SEARCH_QUERY_INVALID": 2,
        "INDEX_INCOMPATIBLE": 3,
        "INDEX_CORRUPT": 3,
        "INDEX_SOURCE_INVALID": 3,
        "OBJECT_NOT_FOUND": 3,
        "INDEX_SOURCE_CHANGED": 4,
        "INDEX_BUSY": 4,
        "INDEX_NOT_FOUND": 5,
    }.get(code, 3)


def _exit_phase3_error(error: DomainError, *, command: str, json_output: bool) -> NoReturn:
    exit_code = _phase3_exit_code(error.code)
    if json_output:
        typer.echo(
            render_json(
                error_envelope(command, exit_code=exit_code, code=error.code, message=str(error))
            )
        )
    else:
        typer.echo(f"{error.code}: {error}", err=True)
    raise typer.Exit(exit_code)


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
        vault = _resolved_vault(ctx)
        result = _capture_service().add(vault, value, requested_type)
    except DomainError as error:
        _exit_add_error(error, json_output=json_output)
    warnings = result.warnings + _refresh_warning(vault, changed=result.created)
    if json_output:
        typer.echo(_success_with_warnings("add", result.data(), warnings))
        return
    action = "Created" if result.created else "Found existing"
    typer.echo(
        f"{action} {result.detected_type} Source {result.source_id}: {result.canonical_identity}"
    )
    _render_warnings(warnings)


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
        vault = _resolved_vault(ctx)
        object_id = _note_service().create(vault, note_type, source_id_value=source)
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(str(object_id))
    _render_warnings(_refresh_warning(vault))


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
        vault = _resolved_vault(ctx)
        evolved_id = _note_service().evolve(vault, object_id, target)
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(str(evolved_id))
    _render_warnings(_refresh_warning(vault))


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
        vault = _resolved_vault(ctx)
        relation = _relation_service().add(
            vault,
            from_id,
            to_id,
            relation_type,
            to_section_value=section,
        )
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(_render_relation(relation))
    _render_warnings(_refresh_warning(vault))


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
        vault = _resolved_vault(ctx)
        relation = _relation_service().remove(
            vault,
            from_id,
            to_id,
            relation_type,
            to_section_value=section,
        )
    except DomainError as error:
        _exit_with_domain_error(error)
    typer.echo(_render_relation(relation))
    _render_warnings(_refresh_warning(vault))


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
        vault = _resolved_vault(ctx)
        result = _source_service().sync(
            vault,
            source_id,
            adopt_remote=adopt_remote,
            accept_attachment_change=accept_attachment_change,
        )
    except DomainError as error:
        _exit_source_error(error, command="source sync", json_output=json_output)
    warnings = result.warnings + _refresh_warning(vault, changed=result.changed)
    if json_output:
        typer.echo(_success_with_warnings("source sync", result.data(), warnings))
        return
    action = "updated" if result.changed else "unchanged"
    typer.echo(f"Source {source_id} is {action}.")
    _render_warnings(warnings)


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
        vault = _resolved_vault(ctx)
        result = _source_service().process(vault, source_id, target)
    except DomainError as error:
        _exit_source_error(error, command="process", json_output=json_output)
    warnings = _refresh_warning(vault, changed=result.changed)
    if json_output:
        typer.echo(_success_with_warnings("process", result.data(), warnings))
        return
    typer.echo(
        f"{source_id}: {result.previous_stage.value} -> {result.current_stage.value}"
        f" ({'changed' if result.changed else 'unchanged'})"
    )
    _render_warnings(warnings)


@app.command("grep")
def grep_command(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Literal text to find in durable files")],
    limit: Annotated[int, typer.Option("--limit", help="Maximum hits (1-200).")] = 20,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Find literal text in configured durable object and relation roots."""

    try:
        result = grep_vault(_resolved_vault(ctx), query, limit)
    except DomainError as error:
        _exit_phase3_error(error, command="grep", json_output=json_output)
    if json_output:
        typer.echo(render_json(success_envelope("grep", result)))
        return
    for hit in cast(list[dict[str, Any]], result["hits"]):
        typer.echo(f"{hit['path']}:{hit['line']}:{hit['column']}: {hit['excerpt']}")
    typer.echo(f"{result['count']} hit(s).")


@app.command("get")
def get_command(
    ctx: typer.Context,
    object_id: Annotated[str, typer.Argument(help="Permanent object ID")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Resolve a permanent object ID without using SQLite."""

    try:
        result = get_object(_resolved_vault(ctx), object_id)
    except DomainError as error:
        _exit_phase3_error(error, command="get", json_output=json_output)
    if json_output:
        typer.echo(render_json(success_envelope("get", result)))
        return
    typer.echo(f"{result['object_id']} {result['path']} {result['checksum']}")
    body = result["body"]
    typer.echo(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2))


def _run_index(ctx: typer.Context, operation: str, json_output: bool) -> None:
    try:
        vault = _resolved_vault(ctx)
        result = (
            _projection().status(vault)
            if operation == "status"
            else _projection().build(vault, rebuild=operation == "rebuild")
        )
    except DomainError as error:
        _exit_phase3_error(error, command=f"index {operation}", json_output=json_output)
    if json_output:
        typer.echo(render_json(success_envelope(f"index {operation}", result)))
        return
    counts = cast(dict[str, int], result["counts"])
    changed = cast(list[str], result["changed_paths"])
    typer.echo(
        f"Index is {result['state']}: {counts['objects']} objects, "
        f"{counts['segments']} segments."
    )
    if changed:
        typer.echo(f"{len(changed)} changed path(s).")


@index_app.command("build")
def index_build(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Create a missing index or incrementally refresh a compatible one."""

    _run_index(ctx, "build", json_output)


@index_app.command("rebuild")
def index_rebuild(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Atomically replace the index from a healthy Vault snapshot."""

    _run_index(ctx, "rebuild", json_output)


@index_app.command("status")
def index_status(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Classify index health without creating or repairing it."""

    _run_index(ctx, "status", json_output)


@app.command("search")
def search_command(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Literal bilingual search query")],
    kind: Annotated[str | None, typer.Option("--kind")] = None,
    subtype: Annotated[str | None, typer.Option("--subtype")] = None,
    visibility: Annotated[str | None, typer.Option("--visibility")] = None,
    record_status: Annotated[str | None, typer.Option("--record-status")] = None,
    workflow_stage: Annotated[str | None, typer.Option("--workflow-stage")] = None,
    maturity: Annotated[str | None, typer.Option("--maturity")] = None,
    review_status: Annotated[str | None, typer.Option("--review-status")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag")] = None,
    role: Annotated[str | None, typer.Option("--role")] = None,
    scope: Annotated[str, typer.Option("--scope")] = ContextScope.TRUSTED_LOCAL.value,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Search a fresh compatible deterministic projection."""

    try:
        selected_scope = ContextScope(scope)
        filters = SearchFilters(
            kind,
            subtype,
            visibility,
            record_status,
            workflow_stage,
            maturity,
            review_status,
            tuple(tag or ()),
            role,
        )
        result = _query_service().search(
            _resolved_vault(ctx), query, filters, selected_scope, limit
        )
    except DomainError as error:
        _exit_phase3_error(error, command="search", json_output=json_output)
    except ValueError:
        _exit_phase3_error(
            DomainError("SEARCH_QUERY_INVALID", "unsupported search scope"),
            command="search",
            json_output=json_output,
        )
    if json_output:
        typer.echo(render_json(success_envelope("search", result)))
        return
    for hit in cast(list[dict[str, Any]], result["hits"]):
        section = f"#{hit['section_id']}" if hit["section_id"] else ""
        classification = cast(dict[str, Any], hit["classification"])
        typer.echo(
            f"{hit['object_id']}{section} [{classification['role']}] "
            f"{hit['title']}: {hit['snippet']}"
        )
    typer.echo(f"{result['count']} hit(s).")


@app.command("context")
def context_command(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Literal bilingual context query")],
    scope: Annotated[str, typer.Option("--scope", help="Required trust scope")],
    limit: Annotated[int, typer.Option("--limit")] = 20,
    max_chars: Annotated[int, typer.Option("--max-chars")] = 12_000,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit one machine-readable JSON document.")
    ] = False,
) -> None:
    """Assemble bounded, cited context under an explicit trust scope."""

    try:
        selected_scope = ContextScope(scope)
        result = _query_service().context(
            _resolved_vault(ctx), query, selected_scope, limit, max_chars
        )
    except DomainError as error:
        _exit_phase3_error(error, command="context", json_output=json_output)
    except ValueError:
        _exit_phase3_error(
            DomainError("SEARCH_QUERY_INVALID", "unsupported context scope"),
            command="context",
            json_output=json_output,
        )
    if json_output:
        typer.echo(render_json(success_envelope("context", result)))
        return
    labels = (
        ("sources", "Sources"),
        ("facts", "Facts"),
        ("human_notes", "Human Notes"),
        ("snippets", "Snippets"),
    )
    for key, label in labels:
        typer.echo(f"{label}:")
        for item in result["groups"][key]:  # type: ignore[index]
            typer.echo(f"- {item['object_id']}: {item['snippet']}")
    typer.echo(f"{result['character_count']} characters; {result['excluded_count']} excluded.")


@app.command("serve")
def serve_command(
    ctx: typer.Context,
    host: Annotated[
        str,
        typer.Option("--host", help="Loopback host: 127.0.0.1, localhost, or ::1."),
    ] = "127.0.0.1",
    port: Annotated[
        str,
        typer.Option("--port", help="Loopback TCP port from 1 through 65535."),
    ] = "8765",
    open_browser: Annotated[
        bool,
        typer.Option("--open-browser", help="Open the local page once after startup."),
    ] = False,
) -> None:
    """Serve the strictly read-only local Web interface."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        _exit_web_error(
            DomainError("WEB_ARGUMENT_INVALID", "host must be an allowed loopback address")
        )
    try:
        selected_port = int(port)
    except ValueError:
        _exit_web_error(DomainError("WEB_ARGUMENT_INVALID", "port must be an integer"))
    if str(selected_port) != port or not 1 <= selected_port <= 65535:
        _exit_web_error(
            DomainError("WEB_ARGUMENT_INVALID", "port must be between 1 and 65535")
        )
    vault = _resolved_vault(ctx)
    try:
        from knowlume.web.server import run_server
    except ModuleNotFoundError:
        _exit_web_error(
            DomainError(
                "WEB_CAPABILITY_UNAVAILABLE",
                "install knowlume[web] to use the local Web interface",
            )
        )
    try:
        run_server(
            vault,
            host=host,
            port=selected_port,
            open_browser=open_browser,
        )
    except KeyboardInterrupt:
        return
    except DomainError as error:
        if error.code != "WEB_SERVER_UNAVAILABLE":
            raise
        _exit_web_error(error)


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
    if apply and report.apply_allowed:
        try:
            vault = VaultService(FilesystemVault()).discover(explicit=root)
        except DomainError:
            return
        _render_warnings(_refresh_warning(vault))


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
