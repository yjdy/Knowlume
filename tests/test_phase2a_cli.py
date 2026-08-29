from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from typer.testing import CliRunner

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.paper_capture import PaperCaptureService
from knowlume.application.sources import SourceService, SourceSyncResult
from knowlume.cli import app
from knowlume.domain.paper import PaperIdentity, normalize_doi
from knowlume.domain.values import DomainError, ObjectId
from knowlume.ports.paper import PaperCaptureRequest
from knowlume.ports.vault import Vault
from knowlume.ports.zotero import (
    AttachmentSelection,
    PaperMetadata,
    PrimaryAttachment,
    ZoteroReference,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
runner = CliRunner()


@dataclass
class Resolver:
    value: PaperMetadata

    def resolve(self, request: PaperCaptureRequest) -> PaperMetadata:
        return self.value


@dataclass
class Zotero:
    value: PaperMetadata
    selection: AttachmentSelection = AttachmentSelection(None, "PAPER_ATTACHMENT_UNAVAILABLE")
    recovered: PrimaryAttachment | None = None

    def metadata(self, reference: ZoteroReference) -> PaperMetadata:
        return self.value

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection:
        return self.selection

    def attachment(self, reference: ZoteroReference, attachment_key: str) -> PrimaryAttachment:
        if self.recovered is None:
            raise DomainError("ZOTERO_ITEM_UNAVAILABLE", "missing")
        return self.recovered


def _setup(tmp_path: Path) -> tuple[Vault, str, SourceService]:
    filesystem, vault, source_id, zotero = _setup_parts(tmp_path)
    return (
        vault,
        source_id,
        SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: NOW),
    )


def _setup_parts(tmp_path: Path) -> tuple[FilesystemVault, Vault, str, Zotero]:
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    metadata = PaperMetadata(
        "CLI Paper",
        ("Ada",),
        2026,
        PaperIdentity(doi=normalize_doi("10.1000/cli")),
        "https://example.test/cli",
        ZoteroReference("user", "0", "ABCD1234"),
        1,
    )
    zotero = Zotero(metadata)
    captured = PaperCaptureService(
        filesystem=filesystem,
        metadata_port=Resolver(metadata),
        zotero_port=zotero,
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8F3",
    ).capture(vault, "10.1000/cli")
    return filesystem, vault, str(captured.source_id), zotero


def _schema(name: str) -> Draft202012Validator:
    document = json.loads(
        (ROOT / "schemas/interfaces" / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(document, format_checker=FormatChecker())


def _json_result(result) -> dict[str, object]:  # type: ignore[no-untyped-def]
    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["interface_version"] == 1
    assert document["success"] is True
    return cast(dict[str, Any], document)


def _assert_golden_json(result, name: str, *, exit_code: int = 0) -> dict[str, object]:  # type: ignore[no-untyped-def]
    expected = json.loads((ROOT / "tests/fixtures/interfaces" / name).read_text(encoding="utf-8"))
    rendered = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert result.exit_code == exit_code
    assert result.stdout == rendered + "\n"
    return cast(dict[str, object], expected)


def test_source_list_show_inbox_and_process_json(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vault, source_id, service = _setup(tmp_path)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    base = ["--vault", str(vault.root)]
    listed = _assert_golden_json(
        runner.invoke(app, [*base, "source", "list", "--json"]),
        "golden-source-list-envelope.json",
    )
    assert not list(_schema("source-list-result-v1").iter_errors(listed["data"]))
    shown = _json_result(runner.invoke(app, [*base, "source", "show", source_id, "--json"]))
    assert not list(_schema("source-show-result-v1").iter_errors(shown["data"]))
    inbox = _json_result(runner.invoke(app, [*base, "inbox", "--json"]))
    assert not list(_schema("source-list-result-v1").iter_errors(inbox["data"]))
    processed = _json_result(
        runner.invoke(app, [*base, "process", source_id, "--to", "reading", "--json"])
    )
    assert not list(_schema("source-workflow-result-v1").iter_errors(processed["data"]))


def test_source_sync_json_and_human_open_error(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vault, source_id, service = _setup(tmp_path)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    base = ["--vault", str(vault.root)]
    synced = _assert_golden_json(
        runner.invoke(app, [*base, "source", "sync", source_id, "--json"]),
        "golden-source-sync-envelope.json",
    )
    assert not list(_schema("source-sync-result-v1").iter_errors(synced["data"]))
    opened = runner.invoke(app, [*base, "source", "open", source_id])
    assert opened.exit_code == 5
    assert "ZOTERO_ITEM_UNAVAILABLE" in opened.stderr


def test_json_errors_stay_machine_readable(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vault, _, service = _setup(tmp_path)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    result = runner.invoke(
        app,
        ["--vault", str(vault.root), "source", "show", "src_01JSTAG7N9Q3V5X8Y2Z4A6B8F9", "--json"],
    )
    assert result.exit_code == 3
    document = json.loads(result.stdout)
    assert document["errors"][0]["code"] == "SOURCE_NOT_FOUND"


def test_process_skip_has_exact_exit_and_golden_json(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vault, source_id, service = _setup(tmp_path)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    result = runner.invoke(
        app,
        ["--vault", str(vault.root), "process", source_id, "--to", "processed", "--json"],
    )
    _assert_golden_json(
        result,
        "golden-process-invalid-envelope.json",
        exit_code=3,
    )


def test_sync_conflict_has_exact_exit_code(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vault, source_id, _ = _setup(tmp_path)

    class ConflictingService:
        def sync(self, *args: object, **kwargs: object) -> object:
            raise DomainError(
                "SOURCE_SYNC_LOCAL_MODIFIED",
                "Zotero-managed Source fields differ from the synchronization baseline",
            )

    monkeypatch.setattr("knowlume.cli._source_service", ConflictingService)
    result = runner.invoke(
        app,
        ["--vault", str(vault.root), "source", "sync", source_id, "--json"],
    )
    assert result.exit_code == 4
    document = json.loads(result.stdout)
    assert document["exit_code"] == 4
    assert document["errors"][0]["code"] == "SOURCE_SYNC_LOCAL_MODIFIED"


@pytest.mark.parametrize(
    ("option", "value", "field"),
    [
        ("--type", "paper", "source_type"),
        ("--stage", "inbox", "workflow_stage"),
        ("--status", "active", "record_status"),
        ("--visibility", "private", "visibility"),
    ],
)
def test_source_list_cli_forwards_each_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    option: str,
    value: str,
    field: str,
) -> None:
    vault, source_id, service = _setup(tmp_path)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    result = _json_result(
        runner.invoke(
            app,
            ["--vault", str(vault.root), "source", "list", option, value, "--json"],
        )
    )
    data = cast(dict[str, Any], result["data"])
    filters = cast(dict[str, object], data["filter"])
    assert filters[field] == value
    assert data["count"] == 1
    sources = cast(list[dict[str, object]], data["sources"])
    assert sources[0]["source_id"] == source_id


def test_source_list_cli_forwards_combined_filters(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vault, _, service = _setup(tmp_path)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    result = _json_result(
        runner.invoke(
            app,
            [
                "--vault",
                str(vault.root),
                "source",
                "list",
                "--type",
                "paper",
                "--stage",
                "inbox",
                "--status",
                "active",
                "--visibility",
                "private",
                "--json",
            ],
        )
    )
    data = cast(dict[str, Any], result["data"])
    assert data["filter"] == {
        "source_type": "paper",
        "workflow_stage": "inbox",
        "record_status": "active",
        "visibility": "private",
    }
    assert data["count"] == 1


def test_phase2a_human_renderers_and_workflow_transitions(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    vault, source_id, service = _setup(tmp_path)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    base = ["--vault", str(vault.root)]

    listed = runner.invoke(app, [*base, "source", "list"])
    assert listed.exit_code == 0
    assert listed.stdout == f"{source_id} paper inbox CLI Paper\n1 source(s).\n"

    shown = runner.invoke(app, [*base, "source", "show", source_id])
    assert shown.exit_code == 0
    assert "# CLI Paper" in shown.stdout

    inbox = runner.invoke(app, [*base, "inbox"])
    assert inbox.exit_code == 0
    assert inbox.stdout == f"{source_id} paper CLI Paper\n1 inbox source(s).\n"

    synced = runner.invoke(app, [*base, "source", "sync", source_id])
    assert synced.exit_code == 0
    assert synced.stdout == f"Source {source_id} is unchanged.\n"
    assert synced.stderr == "WARNING PAPER_ATTACHMENT_UNAVAILABLE\n"

    current = runner.invoke(app, [*base, "process", source_id, "--to", "inbox"])
    assert current.exit_code == 0
    assert current.stdout == f"{source_id}: inbox -> inbox (unchanged)\n"
    for previous, target in [
        ("inbox", "reading"),
        ("reading", "processed"),
        ("processed", "integrated"),
    ]:
        advanced = runner.invoke(app, [*base, "process", source_id, "--to", target])
        assert advanced.exit_code == 0
        assert advanced.stdout == f"{source_id}: {previous} -> {target} (changed)\n"
    final = runner.invoke(app, [*base, "process", source_id, "--to", "integrated"])
    assert final.exit_code == 0
    assert final.stdout == f"{source_id}: integrated -> integrated (unchanged)\n"


def test_source_open_success_invokes_opener_and_renders_human_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem, vault, source_id, zotero = _setup_parts(tmp_path)
    cached = tmp_path / "paper.pdf"
    cached.write_bytes(b"pdf")
    attachment = PrimaryAttachment(
        "EFGH5678",
        2,
        "paper.pdf",
        "application/pdf",
        3,
        "sha256:" + "3" * 64,
        cached,
    )
    zotero.selection = AttachmentSelection(attachment)
    zotero.recovered = attachment
    opened: list[Path] = []
    service = SourceService(
        filesystem=filesystem,
        zotero=zotero,
        opener=opened.append,
        clock=lambda: NOW,
    )
    assert service.sync(vault, source_id).changed
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)

    result = runner.invoke(
        app,
        ["--vault", str(vault.root), "source", "open", source_id],
    )
    assert result.exit_code == 0
    assert result.stdout == f"Opened primary attachment for {source_id}.\n"
    assert opened == [cached]


def test_source_sync_adopt_remote_cli_option(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    fixture = (ROOT / "tests/fixtures/v2/valid/legacy-zotero-only-paper-source.md").read_bytes()
    filesystem.atomic_write(vault, "sources/papers/legacy.md", fixture, None)
    metadata = PaperMetadata(
        "CLI Paper",
        ("Ada",),
        2026,
        PaperIdentity(doi=normalize_doi("10.1000/cli")),
        "https://example.test/cli",
        ZoteroReference("user", "0", "ABCD1234"),
        1,
    )
    service = SourceService(
        filesystem=filesystem,
        zotero=Zotero(metadata),
        clock=lambda: NOW,
    )
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    result = _json_result(
        runner.invoke(
            app,
            [
                "--vault",
                str(vault.root),
                "source",
                "sync",
                "src_01JSTAG7N9Q3V5X8Y2Z4A6B8E1",
                "--adopt-remote",
                "--json",
            ],
        )
    )
    data = cast(dict[str, object], result["data"])
    assert data["changed"] is True
    assert data["baseline_adopted"] is True


@pytest.mark.parametrize("json_output", [False, True], ids=["human", "json"])
def test_source_sync_accept_attachment_change_cli_option_and_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, json_output: bool
) -> None:
    filesystem, vault, source_id, zotero = _setup_parts(tmp_path)
    first = PrimaryAttachment(
        "EFGH5678",
        2,
        "paper.pdf",
        "application/pdf",
        3,
        "sha256:" + "3" * 64,
        tmp_path / "first.pdf",
    )
    second = replace(
        first,
        version=3,
        sha256="sha256:" + "4" * 64,
        cache_path=tmp_path / "second.pdf",
    )
    service = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: NOW)
    zotero.selection = AttachmentSelection(first)
    assert service.sync(vault, source_id).changed
    zotero.selection = AttachmentSelection(second)
    monkeypatch.setattr("knowlume.cli._source_service", lambda: service)
    args = [
        "--vault",
        str(vault.root),
        "source",
        "sync",
        source_id,
        "--accept-attachment-change",
    ]
    if json_output:
        args.append("--json")
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    if json_output:
        document = json.loads(result.stdout)
        assert document["data"]["attachment_changed"] is True
        assert document["warnings"] == [
            {
                "code": "PAPER_ATTACHMENT_ACCEPTED_LOCATORS_REVIEW",
                "message": "Paper Attachment Accepted Locators Review",
            }
        ]
    else:
        assert result.stdout == f"Source {source_id} is updated.\n"
        assert result.stderr == "WARNING PAPER_ATTACHMENT_ACCEPTED_LOCATORS_REVIEW\n"


@pytest.mark.parametrize(
    ("code", "exit_code"),
    [
        ("SOURCE_NOT_FOUND", 3),
        ("SOURCE_TYPE_UNSUPPORTED", 3),
        ("SOURCE_SYNC_ADOPTION_INVALID", 3),
        ("SOURCE_SYNC_INVALID", 3),
        ("SOURCE_WORKFLOW_INVALID", 3),
        ("PAPER_CANONICAL_IDENTITY_MISSING", 3),
        ("PAPER_IDENTITY_CONFLICT", 3),
        ("PAPER_ATTACHMENT_CHANGED", 4),
        ("SOURCE_SYNC_LOCAL_MODIFIED", 4),
        ("SOURCE_SYNC_BASELINE_REQUIRED", 4),
        ("ZOTERO_CAPABILITY_UNAVAILABLE", 5),
        ("ZOTERO_API_UNAVAILABLE", 5),
        ("ZOTERO_PERMISSION_DENIED", 5),
        ("ZOTERO_ITEM_UNAVAILABLE", 5),
        ("ZOTERO_REFERENCE_INVALID", 5),
        ("ZOTERO_RESPONSE_INVALID", 5),
    ],
)
def test_phase2a_public_diagnostics_have_matching_human_and_json_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    exit_code: int,
) -> None:
    vault, source_id, _ = _setup(tmp_path)

    class FailingService:
        def sync(self, *args: object, **kwargs: object) -> SourceSyncResult:
            raise DomainError(code, "frozen diagnostic")

    monkeypatch.setattr("knowlume.cli._source_service", FailingService)
    base = ["--vault", str(vault.root), "source", "sync", source_id]
    human = runner.invoke(app, base)
    assert human.exit_code == exit_code
    assert code in human.stderr
    machine = runner.invoke(app, [*base, "--json"])
    assert machine.exit_code == exit_code
    document = json.loads(machine.stdout)
    assert document["exit_code"] == exit_code
    assert document["errors"] == [{"code": code, "message": "frozen diagnostic"}]


@pytest.mark.parametrize(
    "warning",
    [
        "PAPER_ATTACHMENT_UNAVAILABLE",
        "PAPER_ATTACHMENT_AMBIGUOUS",
        "PAPER_ATTACHMENT_ACCEPTED_LOCATORS_REVIEW",
    ],
)
def test_phase2a_public_warnings_have_human_and_json_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warning: str
) -> None:
    vault, source_id, _ = _setup(tmp_path)

    class WarningService:
        def sync(self, *args: object, **kwargs: object) -> SourceSyncResult:
            return SourceSyncResult(
                ObjectId(source_id),
                False,
                False,
                False,
                NOW,
                (warning,),
            )

    monkeypatch.setattr("knowlume.cli._source_service", WarningService)
    base = ["--vault", str(vault.root), "source", "sync", source_id]
    human = runner.invoke(app, base)
    assert human.exit_code == 0
    assert human.stderr == f"WARNING {warning}\n"
    machine = runner.invoke(app, [*base, "--json"])
    assert machine.exit_code == 0
    document = json.loads(machine.stdout)
    assert document["warnings"] == [
        {"code": warning, "message": warning.replace("_", " ").title()}
    ]
