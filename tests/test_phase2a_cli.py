from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from typer.testing import CliRunner

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.paper_capture import PaperCaptureService
from knowlume.application.sources import SourceService
from knowlume.cli import app
from knowlume.domain.paper import PaperIdentity, normalize_doi
from knowlume.domain.values import DomainError
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

    def metadata(self, reference: ZoteroReference) -> PaperMetadata:
        return self.value

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection:
        return AttachmentSelection(None, "PAPER_ATTACHMENT_UNAVAILABLE")

    def attachment(self, reference: ZoteroReference, attachment_key: str) -> PrimaryAttachment:
        raise AssertionError("no attachment expected")


def _setup(tmp_path: Path) -> tuple[Vault, str, SourceService]:
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
    return (
        vault,
        str(captured.source_id),
        SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: NOW),
    )


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
