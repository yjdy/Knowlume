from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowlume.adapters.contract_v2 import render_object_document
from knowlume.adapters.filesystem import FilesystemVault, checksum_file
from knowlume.application.paper_capture import PaperCaptureService
from knowlume.application.scanning import Finding, scan_vault
from knowlume.application.sources import SourceService
from knowlume.domain.models import ObjectDocument, Source
from knowlume.domain.paper import PaperIdentity, normalize_arxiv, normalize_doi
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
LATER = datetime(2026, 8, 29, 12, tzinfo=UTC)


@dataclass
class Resolver:
    value: PaperMetadata

    def resolve(self, request: PaperCaptureRequest) -> PaperMetadata:
        return self.value


@dataclass
class Zotero:
    metadata_value: PaperMetadata
    selection: AttachmentSelection = AttachmentSelection(None, "PAPER_ATTACHMENT_UNAVAILABLE")
    recovered: PrimaryAttachment | None = None

    def metadata(self, reference: ZoteroReference) -> PaperMetadata:
        return self.metadata_value

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection:
        return self.selection

    def attachment(self, reference: ZoteroReference, attachment_key: str) -> PrimaryAttachment:
        if self.recovered is None:
            raise DomainError("ZOTERO_ITEM_UNAVAILABLE", "missing")
        return self.recovered


def _metadata(*, title: str = "Example Paper", item_version: int = 7) -> PaperMetadata:
    return PaperMetadata(
        title,
        ("Ada Lovelace",),
        2024,
        PaperIdentity(normalize_doi("10.1000/example"), normalize_arxiv("2401.12345v2")),
        "https://example.test/paper",
        ZoteroReference("user", "0", "ABCD1234"),
        item_version,
    )


def _setup(tmp_path: Path) -> tuple[FilesystemVault, Vault, str, Zotero]:
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    metadata = _metadata()
    zotero = Zotero(metadata)
    captured = PaperCaptureService(
        filesystem=filesystem,
        metadata_port=Resolver(metadata),
        zotero_port=zotero,
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8F2",
    ).capture(vault, "10.1000/example")
    return filesystem, vault, str(captured.source_id), zotero


def test_source_list_show_and_inbox_are_scanner_backed(tmp_path: Path) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    service = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: LATER)
    listed = service.list(vault, source_type="paper")
    assert listed["count"] == 1
    assert listed["sources"][0]["source_id"] == source_id
    assert service.list(vault, inbox=True)["filter"]["workflow_stage"] == "inbox"
    shown = service.show(vault, source_id)
    assert shown["source"]["id"] == source_id
    assert not Path(shown["path"]).is_absolute()
    assert "# Example Paper" in service.rendered(vault, source_id)

    original = scan_vault(vault).objects[next(iter(scan_vault(vault).objects))].document.object
    assert isinstance(original, Source)
    second = replace(
        original,
        id=type(original.id)("src_01JSTAG7N9Q3V5X8Y2Z4A6B8F4"),
        title="Newer update, older capture",
        created=original.created.replace(day=27),
        updated=original.updated.replace(day=30),
    )
    filesystem.atomic_write(
        vault,
        f"sources/papers/{second.id}.md",
        render_object_document(ObjectDocument(second, "# Newer update, older capture")).encode(),
        None,
    )
    assert [item["source_id"] for item in service.list(vault)["sources"]] == [
        str(second.id),
        source_id,
    ]
    assert [item["source_id"] for item in service.list(vault, inbox=True)["sources"]] == [
        str(second.id),
        source_id,
    ]


def test_workflow_is_adjacent_and_current_stage_is_byte_preserving(tmp_path: Path) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    service = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: LATER)
    path = vault.root / service.show(vault, source_id)["path"]
    before = path.read_bytes()
    current = service.process(vault, source_id, "inbox")
    assert not current.changed and path.read_bytes() == before
    with pytest.raises(DomainError) as caught:
        service.process(vault, source_id, "processed")
    assert caught.value.code == "SOURCE_WORKFLOW_INVALID"
    assert service.process(vault, source_id, "reading").changed
    with pytest.raises(DomainError):
        service.process(vault, source_id, "inbox")
    assert service.process(vault, source_id, "processed").changed
    assert service.process(vault, source_id, "integrated").changed
    assert not service.process(vault, source_id, "integrated").changed


def test_sync_noop_is_byte_preserving_and_remote_update_preserves_human_fields(
    tmp_path: Path,
) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    service = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: LATER)
    path = vault.root / service.show(vault, source_id)["path"]
    before = path.read_bytes()
    result = service.sync(vault, source_id)
    assert result.changed is False
    assert path.read_bytes() == before

    zotero.metadata_value = _metadata(title="Updated Remote Title", item_version=8)
    changed = service.sync(vault, source_id)
    assert changed.changed
    source = service.show(vault, source_id)["source"]
    assert source["title"] == "Updated Remote Title"
    assert source["visibility"] == "private"
    assert source["workflow_stage"] == "inbox"
    assert source["tags"] == []


def test_local_managed_edit_blocks_sync(tmp_path: Path) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    scanned = scan_vault(vault).objects[next(iter(scan_vault(vault).objects))]
    source = scanned.document.object
    assert isinstance(source, Source)
    edited = replace(source, title="Local edit")
    filesystem.atomic_write(
        vault,
        scanned.path,
        render_object_document(replace(scanned.document, object=edited)).encode(),
        scanned.checksum,
    )
    with pytest.raises(DomainError) as caught:
        SourceService(filesystem=filesystem, zotero=zotero).sync(vault, source_id)
    assert caught.value.code == "SOURCE_SYNC_LOCAL_MODIFIED"


def test_legacy_baseline_requires_explicit_adoption(tmp_path: Path) -> None:
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    fixture = (ROOT / "tests/fixtures/v2/valid/legacy-zotero-only-paper-source.md").read_bytes()
    relative = "sources/papers/legacy.md"
    filesystem.atomic_write(vault, relative, fixture, None)
    source_id = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8E1"
    zotero = Zotero(_metadata())
    service = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: LATER)
    with pytest.raises(DomainError) as caught:
        service.sync(vault, source_id)
    assert caught.value.code == "SOURCE_SYNC_BASELINE_REQUIRED"
    adopted = service.sync(vault, source_id, adopt_remote=True)
    assert adopted.changed and adopted.baseline_adopted


def test_matching_legacy_fields_adopt_first_baseline_automatically(tmp_path: Path) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    scanned = scan_vault(vault).objects[next(iter(scan_vault(vault).objects))]
    source = scanned.document.object
    assert isinstance(source, Source)
    legacy = replace(source, managed_fields_hash=None, synced_at=None)
    filesystem.atomic_write(
        vault,
        scanned.path,
        render_object_document(replace(scanned.document, object=legacy)).encode(),
        scanned.checksum,
    )
    adopted = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: LATER).sync(
        vault, source_id
    )
    assert adopted.changed and adopted.baseline_adopted


def test_sync_rejects_identity_collision_with_another_source(tmp_path: Path) -> None:
    filesystem, vault, _, zotero = _setup(tmp_path)
    fixture = (ROOT / "tests/fixtures/v2/valid/legacy-zotero-only-paper-source.md").read_bytes()
    filesystem.atomic_write(vault, "sources/papers/legacy.md", fixture, None)
    service = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: LATER)
    with pytest.raises(DomainError) as caught:
        service.sync(vault, "src_01JSTAG7N9Q3V5X8Y2Z4A6B8E1", adopt_remote=True)
    assert caught.value.code == "PAPER_IDENTITY_CONFLICT"


@pytest.mark.parametrize(
    "remote_identity",
    [
        PaperIdentity(arxiv=normalize_arxiv("2401.12345v9")),
        PaperIdentity(
            doi=normalize_doi("10.1000/replaced"),
            arxiv=normalize_arxiv("2401.12345"),
        ),
    ],
    ids=["doi-removed", "doi-replaced"],
)
def test_sync_rejects_identity_removal_or_replacement_before_write(
    tmp_path: Path, remote_identity: PaperIdentity
) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    service = SourceService(filesystem=filesystem, zotero=zotero, clock=lambda: LATER)
    path = vault.root / service.show(vault, source_id)["path"]
    before = path.read_bytes()
    zotero.metadata_value = replace(_metadata(item_version=8), identity=remote_identity)

    with pytest.raises(DomainError) as caught:
        service.sync(vault, source_id)

    assert caught.value.code == "PAPER_IDENTITY_CONFLICT"
    assert path.read_bytes() == before


def test_attachment_hash_mismatch_blocks_open_and_sync_without_acceptance(tmp_path: Path) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    cached = tmp_path / "paper.pdf"
    cached.write_bytes(b"changed")
    attachment = PrimaryAttachment(
        "EFGH5678", 2, "paper.pdf", "application/pdf", 7, "sha256:" + "3" * 64, cached
    )
    zotero.selection = AttachmentSelection(attachment)
    service = SourceService(
        filesystem=filesystem, zotero=zotero, opener=lambda _: None, clock=lambda: LATER
    )
    first = service.sync(vault, source_id)
    assert first.changed
    original_hash = service.show(vault, source_id)["source"]["attachment_sha256"]
    replacement = replace(attachment, version=3, sha256="sha256:" + "4" * 64)
    zotero.selection = AttachmentSelection(replacement)
    zotero.recovered = replacement
    with pytest.raises(DomainError) as caught:
        service.sync(vault, source_id)
    assert caught.value.code == "PAPER_ATTACHMENT_CHANGED"
    assert service.show(vault, source_id)["source"]["attachment_sha256"] == original_hash
    accepted = service.sync(vault, source_id, accept_attachment_change=True)
    assert accepted.attachment_changed
    path = service.open(vault, source_id)
    assert path == cached
    zotero.recovered = replace(replacement, sha256="sha256:" + "5" * 64)
    with pytest.raises(DomainError) as open_error:
        service.open(vault, source_id)
    assert open_error.value.code == "PAPER_ATTACHMENT_CHANGED"


def test_sync_uses_expected_checksum(tmp_path: Path) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    zotero.metadata_value = _metadata(title="Changed", item_version=8)

    class RacingFilesystem(FilesystemVault):
        def atomic_write(self, vault_arg, relative_path, content, expected_checksum):  # type: ignore[no-untyped-def]
            path = vault_arg.root / relative_path
            path.write_bytes(b"newer")
            return super().atomic_write(vault_arg, relative_path, content, expected_checksum)

    with pytest.raises(DomainError) as caught:
        SourceService(filesystem=RacingFilesystem(environment={}), zotero=zotero).sync(
            vault, source_id
        )
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    assert checksum_file(vault.root / f"sources/papers/{source_id}.md") is not None


def test_post_write_sync_scan_failure_restores_original_bytes(tmp_path: Path) -> None:
    filesystem, vault, source_id, zotero = _setup(tmp_path)
    zotero.metadata_value = _metadata(title="Changed", item_version=8)
    path = vault.root / f"sources/papers/{source_id}.md"
    original = path.read_bytes()
    scans = 0

    def scanner(vault_value):  # type: ignore[no-untyped-def]
        nonlocal scans
        scans += 1
        result = scan_vault(vault_value)
        if scans == 1:
            return result
        return type(result)(
            result.objects,
            result.relation_shards,
            (
                Finding(
                    code="POST_WRITE_REJECTED",
                    severity="error",
                    category="contract",
                    message="simulated acceptance failure",
                ),
            ),
            result.files_scanned,
        )

    service = SourceService(
        filesystem=filesystem,
        zotero=zotero,
        clock=lambda: LATER,
        scanner=scanner,
    )
    with pytest.raises(DomainError) as caught:
        service.sync(vault, source_id)
    assert caught.value.code == "SOURCE_SYNC_INVALID"
    assert path.read_bytes() == original
