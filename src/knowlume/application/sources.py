from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowlume.adapters.contract_v2 import object_data, render_object_document
from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.paper_capture import _managed_fields
from knowlume.application.paper_identity import find_existing_paper, source_identity
from knowlume.application.scanning import ScannedObject, ScanResult, scan_vault
from knowlume.domain.models import Source
from knowlume.domain.paper import managed_fields_hash
from knowlume.domain.values import (
    DomainError,
    ObjectId,
    RecordStatus,
    SourceType,
    Visibility,
    WorkflowStage,
    enum_value,
)
from knowlume.ports.vault import Vault
from knowlume.ports.zotero import AttachmentSelection, PaperMetadata, ZoteroPort, ZoteroReference

_STAGES = (
    WorkflowStage.INBOX,
    WorkflowStage.READING,
    WorkflowStage.PROCESSED,
    WorkflowStage.INTEGRATED,
)


@dataclass(frozen=True)
class SourceSyncResult:
    source_id: ObjectId
    changed: bool
    baseline_adopted: bool
    attachment_changed: bool
    synced_at: datetime
    warnings: tuple[str, ...] = ()

    def data(self) -> dict[str, Any]:
        return {
            "source_id": str(self.source_id),
            "changed": self.changed,
            "baseline_adopted": self.baseline_adopted,
            "attachment_changed": self.attachment_changed,
            "synced_at": self.synced_at.isoformat(),
        }


@dataclass(frozen=True)
class WorkflowResult:
    source_id: ObjectId
    previous_stage: WorkflowStage
    current_stage: WorkflowStage
    changed: bool
    updated: str

    def data(self) -> dict[str, Any]:
        return {
            "source_id": str(self.source_id),
            "previous_stage": self.previous_stage.value,
            "current_stage": self.current_stage.value,
            "changed": self.changed,
            "updated": self.updated,
        }


def open_local_file(path: Path) -> None:
    if sys.platform == "win32":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise DomainError("ZOTERO_API_UNAVAILABLE", "system file opener is unavailable")
        startfile(str(path))
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.Popen(  # noqa: S603
            [command, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise DomainError("ZOTERO_API_UNAVAILABLE", "system file opener is unavailable") from error


class SourceService:
    def __init__(
        self,
        *,
        filesystem: FilesystemVault,
        zotero: ZoteroPort,
        opener: Callable[[Path], None] = open_local_file,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        scanner: Callable[[Vault], ScanResult] = scan_vault,
    ) -> None:
        self._filesystem = filesystem
        self._zotero = zotero
        self._opener = opener
        self._clock = clock
        self._scanner = scanner

    def _healthy_scan(self, vault: Vault) -> ScanResult:
        result = self._scanner(vault)
        if not result.healthy:
            raise DomainError("VAULT_INVALID", "Vault must pass scan before Source operations")
        return result

    def _source(self, result: ScanResult, value: str) -> tuple[Source, ScannedObject]:
        object_id = ObjectId(value)
        scanned = result.objects.get(object_id)
        if scanned is None or not isinstance(scanned.document.object, Source):
            raise DomainError("SOURCE_NOT_FOUND", "Source ID does not exist")
        return scanned.document.object, scanned

    def list(
        self,
        vault: Vault,
        *,
        source_type: str | None = None,
        workflow_stage: str | None = None,
        record_status: str | None = None,
        visibility: str | None = None,
        inbox: bool = False,
    ) -> dict[str, Any]:
        type_value = (
            enum_value(SourceType, source_type, field="Source type") if source_type else None
        )
        stage_value = (
            enum_value(WorkflowStage, workflow_stage, field="workflow stage")
            if workflow_stage
            else None
        )
        status_value = (
            enum_value(RecordStatus, record_status, field="record status")
            if record_status
            else None
        )
        visibility_value = (
            enum_value(Visibility, visibility, field="visibility") if visibility else None
        )
        if inbox:
            stage_value = WorkflowStage.INBOX
        result = self._healthy_scan(vault)
        sources = [
            scanned.document.object
            for scanned in result.objects.values()
            if isinstance(scanned.document.object, Source)
        ]
        sources = [
            source
            for source in sources
            if (type_value is None or source.source_type is type_value)
            and (stage_value is None or source.workflow_stage is stage_value)
            and (status_value is None or source.record_status is status_value)
            and (visibility_value is None or source.visibility is visibility_value)
        ]
        sources.sort(key=lambda source: str(source.id))
        sources.sort(
            key=lambda source: source.created if inbox else source.updated, reverse=not inbox
        )
        items = [
            {
                "source_id": str(source.id),
                "source_type": source.source_type.value,
                "title": source.title,
                "visibility": source.visibility.value,
                "record_status": source.record_status.value,
                "workflow_stage": source.workflow_stage.value,
                "created": source.created.isoformat(),
                "updated": source.updated.isoformat(),
            }
            for source in sources
        ]
        return {
            "filter": {
                "source_type": type_value.value if type_value else None,
                "workflow_stage": stage_value.value if stage_value else None,
                "record_status": status_value.value if status_value else None,
                "visibility": visibility_value.value if visibility_value else None,
            },
            "sources": items,
            "count": len(items),
        }

    def show(self, vault: Vault, source_id: str) -> dict[str, Any]:
        source, scanned = self._source(self._healthy_scan(vault), source_id)
        return {"source": object_data(source), "path": scanned.path, "checksum": scanned.checksum}

    def rendered(self, vault: Vault, source_id: str) -> str:
        _, scanned = self._source(self._healthy_scan(vault), source_id)
        return render_object_document(scanned.document)

    @staticmethod
    def _reference(source: Source) -> ZoteroReference:
        if not source.zotero_library_id or not source.zotero_key:
            raise DomainError("ZOTERO_ITEM_UNAVAILABLE", "Source has no Zotero recovery route")
        library_type = source.zotero_library_type or "user"
        library_id = "0" if source.zotero_library_id == "personal" else source.zotero_library_id
        return ZoteroReference(library_type, library_id, source.zotero_key)

    def open(self, vault: Vault, source_id: str) -> Path:
        source, _ = self._source(self._healthy_scan(vault), source_id)
        if source.source_type is not SourceType.PAPER:
            raise DomainError("SOURCE_TYPE_UNSUPPORTED", "Zotero open supports Paper Sources only")
        if not source.attachment_key:
            raise DomainError(
                "ZOTERO_ITEM_UNAVAILABLE", "Source has no recorded primary attachment"
            )
        recovered = self._zotero.attachment(self._reference(source), source.attachment_key)
        if source.attachment_sha256 and recovered.sha256 != source.attachment_sha256:
            raise DomainError(
                "PAPER_ATTACHMENT_CHANGED", "recovered attachment does not match recorded SHA-256"
            )
        self._opener(recovered.cache_path)
        return recovered.cache_path

    @staticmethod
    def _remote_source(
        source: Source,
        metadata: PaperMetadata,
        selection: AttachmentSelection,
    ) -> Source:
        attachment = selection.attachment
        identity = metadata.identity
        assert identity is not None
        return replace(
            source,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            doi=str(identity.doi) if identity.doi else None,
            arxiv_id=identity.arxiv.base_id if identity.arxiv else None,
            arxiv_version=identity.arxiv.version if identity.arxiv else None,
            canonical_url=metadata.canonical_url,
            attachment_key=attachment.key if attachment else source.attachment_key,
            attachment_version=attachment.version if attachment else source.attachment_version,
            attachment_filename=attachment.filename if attachment else source.attachment_filename,
            attachment_media_type=attachment.media_type
            if attachment
            else source.attachment_media_type,
            attachment_size=attachment.size if attachment else source.attachment_size,
            attachment_sha256=attachment.sha256 if attachment else source.attachment_sha256,
        )

    def sync(
        self,
        vault: Vault,
        source_id: str,
        *,
        adopt_remote: bool = False,
        accept_attachment_change: bool = False,
    ) -> SourceSyncResult:
        result = self._healthy_scan(vault)
        source, scanned = self._source(result, source_id)
        if source.source_type is not SourceType.PAPER:
            raise DomainError("SOURCE_TYPE_UNSUPPORTED", "Zotero sync supports Paper Sources only")
        if adopt_remote and source.managed_fields_hash is not None:
            raise DomainError(
                "SOURCE_SYNC_ADOPTION_INVALID",
                "Remote adoption is only valid for a Source without a baseline",
            )
        reference = self._reference(source)
        current_hash = managed_fields_hash(_managed_fields(source))
        if source.managed_fields_hash and current_hash != source.managed_fields_hash:
            raise DomainError(
                "SOURCE_SYNC_LOCAL_MODIFIED",
                "Zotero-managed Source fields differ from the synchronization baseline",
            )
        metadata = self._zotero.metadata(reference)
        if metadata.identity is None:
            raise DomainError(
                "PAPER_CANONICAL_IDENTITY_MISSING",
                "Zotero metadata has neither DOI nor arXiv identity",
            )
        existing_identity = source_identity(source)
        if existing_identity is not None:
            if existing_identity.doi and metadata.identity.doi != existing_identity.doi:
                raise DomainError("PAPER_IDENTITY_CONFLICT", "Zotero DOI was removed or replaced")
            if existing_identity.arxiv and (
                metadata.identity.arxiv is None
                or metadata.identity.arxiv.base_id != existing_identity.arxiv.base_id
            ):
                raise DomainError(
                    "PAPER_IDENTITY_CONFLICT", "Zotero arXiv ID was removed or replaced"
                )
        all_sources = [
            item.document.object
            for item in result.objects.values()
            if isinstance(item.document.object, Source) and item.document.object.id != source.id
        ]
        collision = find_existing_paper(all_sources, metadata.identity)
        if collision is not None:
            raise DomainError(
                "PAPER_IDENTITY_CONFLICT", "Zotero identity belongs to another Source"
            )
        selection = self._zotero.primary_attachment(reference)
        warning_list = [selection.warning_code] if selection.warning_code else []
        remote = self._remote_source(source, metadata, selection)
        attachment_changed = bool(
            source.attachment_sha256
            and remote.attachment_sha256
            and source.attachment_sha256 != remote.attachment_sha256
        )
        if attachment_changed and not accept_attachment_change:
            raise DomainError(
                "PAPER_ATTACHMENT_CHANGED",
                "Zotero primary attachment differs from recorded material",
            )
        if attachment_changed:
            warning_list.append("PAPER_ATTACHMENT_ACCEPTED_LOCATORS_REVIEW")
        warnings = tuple(warning_list)
        remote_hash = managed_fields_hash(_managed_fields(remote))
        baseline_adopted = source.managed_fields_hash is None
        if baseline_adopted and current_hash != remote_hash and not adopt_remote:
            raise DomainError(
                "SOURCE_SYNC_BASELINE_REQUIRED",
                "Legacy Source differs from Zotero; use explicit remote adoption",
            )
        now = self._clock()
        no_op = (
            source.managed_fields_hash == remote_hash
            and source.zotero_item_version == metadata.item_version
            and source.synced_at is not None
        )
        if no_op:
            assert source.synced_at is not None
            return SourceSyncResult(source.id, False, False, False, source.synced_at, warnings)
        synchronized = replace(
            remote,
            zotero_item_version=metadata.item_version,
            synced_at=now,
            managed_fields_hash=remote_hash,
            updated=now.date(),
        )
        document = replace(scanned.document, object=synchronized)
        original = (vault.root / scanned.path).read_bytes()
        replacement_checksum = self._filesystem.atomic_write(
            vault,
            scanned.path,
            render_object_document(document).encode("utf-8"),
            scanned.checksum,
        )
        accepted = self._scanner(vault)
        if not accepted.healthy or synchronized.id not in accepted.objects:
            self._filesystem.atomic_write(vault, scanned.path, original, replacement_checksum)
            raise DomainError(
                "SOURCE_SYNC_INVALID", "synchronized Source failed scanner validation"
            )
        return SourceSyncResult(
            source.id, True, baseline_adopted, attachment_changed, now, warnings
        )

    def process(self, vault: Vault, source_id: str, target: str) -> WorkflowResult:
        target_stage = enum_value(WorkflowStage, target, field="workflow target")
        result = self._healthy_scan(vault)
        source, scanned = self._source(result, source_id)
        previous = source.workflow_stage
        if target_stage is previous:
            return WorkflowResult(source.id, previous, previous, False, source.updated.isoformat())
        if _STAGES.index(target_stage) != _STAGES.index(previous) + 1:
            raise DomainError(
                "SOURCE_WORKFLOW_INVALID",
                "Source workflow transitions must advance exactly one adjacent stage",
            )
        today = self._clock().date()
        updated = replace(source, workflow_stage=target_stage, updated=today)
        original = (vault.root / scanned.path).read_bytes()
        replacement_checksum = self._filesystem.atomic_write(
            vault,
            scanned.path,
            render_object_document(replace(scanned.document, object=updated)).encode("utf-8"),
            scanned.checksum,
        )
        accepted = self._scanner(vault)
        if not accepted.healthy:
            self._filesystem.atomic_write(vault, scanned.path, original, replacement_checksum)
            raise DomainError("SOURCE_WORKFLOW_INVALID", "updated Source failed scanner validation")
        return WorkflowResult(source.id, previous, target_stage, True, today.isoformat())
