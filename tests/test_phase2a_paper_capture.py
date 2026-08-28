from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.paper_capture import PaperCaptureService
from knowlume.application.scanning import Finding, scan_vault
from knowlume.domain.paper import PaperIdentity, normalize_arxiv, normalize_doi
from knowlume.domain.values import DomainError
from knowlume.ports.paper import PaperCaptureRequest
from knowlume.ports.vault import Vault
from knowlume.ports.zotero import AttachmentSelection, PaperMetadata, ZoteroReference

ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


@dataclass
class Resolver:
    metadata_value: PaperMetadata | None = None
    error: DomainError | None = None

    def resolve(self, request: PaperCaptureRequest) -> PaperMetadata:
        if self.error:
            raise self.error
        assert self.metadata_value is not None
        return self.metadata_value


@dataclass
class Zotero:
    selection: AttachmentSelection = AttachmentSelection(None, "PAPER_ATTACHMENT_UNAVAILABLE")
    error: DomainError | None = None

    def metadata(self, reference: ZoteroReference) -> PaperMetadata:
        raise AssertionError("capture uses the metadata resolver")

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection:
        if self.error:
            raise self.error
        return self.selection

    def attachment(self, reference: ZoteroReference, attachment_key: str):  # type: ignore[no-untyped-def]
        assert self.selection.attachment is not None
        return self.selection.attachment


def _metadata(*, identity: PaperIdentity | None = None) -> PaperMetadata:
    return PaperMetadata(
        "Example Paper",
        ("Ada Lovelace",),
        2024,
        identity
        or PaperIdentity(normalize_doi("10.1000/example"), normalize_arxiv("2401.12345v2")),
        "https://example.test/paper",
        ZoteroReference("user", "0", "ABCD1234"),
        7,
    )


def _vault(tmp_path: Path) -> tuple[FilesystemVault, Vault]:
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    return filesystem, vault


def _service(
    filesystem: FilesystemVault, resolver: Resolver, zotero: Zotero | None = None
) -> PaperCaptureService:
    return PaperCaptureService(
        filesystem=filesystem,
        metadata_port=resolver,
        zotero_port=zotero or Zotero(),
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8F0",
    )


def test_capture_is_idempotent_and_contains_no_cache_path(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    service = _service(filesystem, Resolver(_metadata()))
    first = service.capture(vault, "https://doi.org/10.1000/example")
    second = service.capture(vault, "arXiv:2401.12345v3")
    assert first.created is True
    assert second.created is False
    assert first.source_id == second.source_id
    result = scan_vault(vault)
    assert len(result.objects) == 1 and result.healthy
    text = (vault.root / next(iter(result.objects.values())).path).read_text(encoding="utf-8")
    assert str(tmp_path) not in text
    assert "attachment body" not in text


def test_zotero_only_metadata_is_ineligible_and_writes_nothing(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    metadata = _metadata()
    metadata = PaperMetadata(
        metadata.title,
        metadata.authors,
        metadata.year,
        None,
        metadata.canonical_url,
        metadata.zotero,
        metadata.item_version,
    )
    with pytest.raises(DomainError) as caught:
        _service(filesystem, Resolver(metadata)).capture(vault, metadata.zotero)
    assert caught.value.code == "PAPER_CANONICAL_IDENTITY_MISSING"
    assert scan_vault(vault).objects == {}


def test_adapter_failure_writes_nothing(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    service = _service(
        filesystem,
        Resolver(_metadata()),
        Zotero(error=DomainError("ZOTERO_API_UNAVAILABLE", "offline")),
    )
    with pytest.raises(DomainError) as caught:
        service.capture(vault, "10.1000/example")
    assert caught.value.code == "ZOTERO_API_UNAVAILABLE"
    assert scan_vault(vault).objects == {}


def test_split_identity_conflict_writes_no_second_source(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
    first = _service(filesystem, Resolver(_metadata()))
    first.capture(vault, "10.1000/example")
    other = _metadata(
        identity=PaperIdentity(normalize_doi("10.1000/other"), normalize_arxiv("2501.54321"))
    )
    PaperCaptureService(
        filesystem=filesystem,
        metadata_port=Resolver(other),
        zotero_port=Zotero(),
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8F1",
    ).capture(vault, "10.1000/other")
    conflict = _metadata(
        identity=PaperIdentity(normalize_doi("10.1000/example"), normalize_arxiv("2501.54321"))
    )
    with pytest.raises(DomainError) as caught:
        _service(filesystem, Resolver(conflict)).capture(vault, "10.1000/example")
    assert caught.value.code == "PAPER_IDENTITY_CONFLICT"
    assert len(scan_vault(vault).objects) == 2


class InterruptedFilesystem(FilesystemVault):
    def atomic_write(self, *args: object, **kwargs: object) -> str:
        raise DomainError("VAULT_WRITE_CONFLICT", "interrupted")


def test_write_failure_leaves_no_partial_source(tmp_path: Path) -> None:
    base, vault = _vault(tmp_path)
    filesystem = InterruptedFilesystem(environment={})
    service = _service(filesystem, Resolver(_metadata()))
    with pytest.raises(DomainError) as caught:
        service.capture(vault, "10.1000/example")
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    assert scan_vault(vault).objects == {}


def test_post_write_scan_failure_rolls_back_new_source(tmp_path: Path) -> None:
    filesystem, vault = _vault(tmp_path)
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

    service = PaperCaptureService(
        filesystem=filesystem,
        metadata_port=Resolver(_metadata()),
        zotero_port=Zotero(),
        clock=lambda: NOW,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8F5",
        scanner=scanner,
    )
    with pytest.raises(DomainError) as caught:
        service.capture(vault, "10.1000/example")
    assert caught.value.code == "PAPER_CAPTURE_INVALID"
    assert scan_vault(vault).objects == {}
