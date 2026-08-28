from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.paper_identity import find_existing_paper
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.domain.models import ObjectDocument, Source
from knowlume.domain.paper import managed_fields_hash, normalize_arxiv, normalize_doi
from knowlume.domain.values import (
    DomainError,
    ObjectId,
    RecordStatus,
    SourceType,
    Visibility,
    WorkflowStage,
)
from knowlume.ids import new_ulid
from knowlume.ports.paper import PaperCaptureRequest, PaperMetadataPort
from knowlume.ports.vault import Vault
from knowlume.ports.zotero import AttachmentSelection, ZoteroPort, ZoteroReference


@dataclass(frozen=True)
class PaperCaptureResult:
    source_id: ObjectId
    canonical_identity: str
    created: bool
    warnings: tuple[str, ...] = ()


def paper_capture_request(
    value: str | ZoteroReference,
) -> PaperCaptureRequest:
    if isinstance(value, ZoteroReference):
        return PaperCaptureRequest(
            f"zotero:{value.library_type}:{value.library_id}:{value.item_key}", zotero=value
        )
    stripped = value.strip()
    try:
        return PaperCaptureRequest(stripped, doi=normalize_doi(stripped))
    except DomainError:
        pass
    try:
        return PaperCaptureRequest(stripped, arxiv=normalize_arxiv(stripped))
    except DomainError as error:
        raise DomainError(
            "ADD_INPUT_INVALID", "Paper input is not a DOI or arXiv identifier"
        ) from error


def _managed_fields(source: Source) -> dict[str, object]:
    return {
        "title": source.title,
        "authors": list(source.authors),
        "year": source.year,
        "doi": source.doi,
        "arxiv_id": source.arxiv_id,
        "arxiv_version": source.arxiv_version,
        "canonical_url": source.canonical_url,
        "attachment_key": source.attachment_key,
        "attachment_version": source.attachment_version,
        "attachment_filename": source.attachment_filename,
        "attachment_media_type": source.attachment_media_type,
        "attachment_size": source.attachment_size,
        "attachment_sha256": source.attachment_sha256,
    }


class PaperCaptureService:
    def __init__(
        self,
        *,
        filesystem: FilesystemVault,
        metadata_port: PaperMetadataPort,
        zotero_port: ZoteroPort,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        ulid_factory: Callable[[], str] = new_ulid,
        scanner: Callable[[Vault], ScanResult] = scan_vault,
    ) -> None:
        self._filesystem = filesystem
        self._metadata_port = metadata_port
        self._zotero_port = zotero_port
        self._clock = clock
        self._ulid_factory = ulid_factory
        self._scanner = scanner

    def capture(self, vault: Vault, value: str | ZoteroReference) -> PaperCaptureResult:
        current = self._scanner(vault)
        if not current.healthy:
            raise DomainError("VAULT_INVALID", "Vault must pass scan before Paper capture")
        request = paper_capture_request(value)
        metadata = self._metadata_port.resolve(request)
        if metadata.identity is None:
            raise DomainError(
                "PAPER_CANONICAL_IDENTITY_MISSING",
                "Resolved Paper metadata has neither DOI nor arXiv identity",
            )
        sources = [
            scanned.document.object
            for scanned in current.objects.values()
            if isinstance(scanned.document.object, Source)
        ]
        existing = find_existing_paper(sources, metadata.identity)
        if existing is not None:
            return PaperCaptureResult(existing, metadata.identity.canonical, False)

        warnings: list[str] = []
        selection = AttachmentSelection(None)
        if metadata.zotero:
            selection = self._zotero_port.primary_attachment(metadata.zotero)
            if selection.warning_code:
                warnings.append(selection.warning_code)
        attachment = selection.attachment
        now = self._clock()
        source_id = ObjectId(f"src_{self._ulid_factory()}")
        source = Source(
            id=source_id,
            source_type=SourceType.PAPER,
            title=metadata.title,
            visibility=Visibility.PRIVATE,
            record_status=RecordStatus.ACTIVE,
            workflow_stage=WorkflowStage.INBOX,
            created=now.date(),
            updated=now.date(),
            tags=(),
            canonical_url=metadata.canonical_url,
            zotero_library_id=metadata.zotero.library_id,
            zotero_library_type=metadata.zotero.library_type,
            zotero_key=metadata.zotero.item_key,
            zotero_item_version=metadata.item_version,
            synced_at=now,
            attachment_key=attachment.key if attachment else None,
            attachment_version=attachment.version if attachment else None,
            attachment_filename=attachment.filename if attachment else None,
            attachment_media_type=attachment.media_type if attachment else None,
            attachment_size=attachment.size if attachment else None,
            attachment_sha256=attachment.sha256 if attachment else None,
            doi=str(metadata.doi) if metadata.doi else None,
            arxiv_id=metadata.arxiv.base_id if metadata.arxiv else None,
            arxiv_version=metadata.arxiv.version if metadata.arxiv else None,
            year=metadata.year,
            authors=metadata.authors,
        )
        source = replace(source, managed_fields_hash=managed_fields_hash(_managed_fields(source)))
        document = ObjectDocument(
            source,
            f"# {source.title}\n\n## Capture notes\n\nCaptured by the internal Paper service.",
        )
        content = render_object_document(document).encode("utf-8")
        # Fail before touching durable state if the constructed representation does not round-trip.
        if parse_object_document(content.decode("utf-8")) != document:
            raise DomainError("PAPER_CAPTURE_INVALID", "constructed Source does not round-trip")
        relative = f"{vault.config.sources}/papers/{source_id}.md"
        written_checksum = self._filesystem.atomic_write(vault, relative, content, None)
        accepted = self._scanner(vault)
        scanned = accepted.objects.get(source_id)
        if not accepted.healthy or scanned is None:
            self._filesystem.atomic_delete(vault, relative, written_checksum)
            raise DomainError(
                "PAPER_CAPTURE_INVALID", "captured Source did not pass scanner validation"
            )
        return PaperCaptureResult(
            source_id,
            metadata.identity.canonical,
            True,
            tuple(warnings),
        )
