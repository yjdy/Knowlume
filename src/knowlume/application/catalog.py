from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from typing import Any, Literal, cast

from knowlume.application.query import get_object
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.domain.models import AIArtifact, Note, Source
from knowlume.domain.values import (
    DomainError,
    Maturity,
    NoteType,
    ObjectId,
    RecordStatus,
    ReviewStatus,
    SourceType,
    Visibility,
    WorkflowStage,
    enum_value,
)
from knowlume.ports.vault import Vault

CATALOG_PAGE_SIZE = 50

type IndexStatusReader = Callable[[Vault, ScanResult], dict[str, object]]


@dataclass(frozen=True)
class CatalogPage:
    kind: Literal["source", "note", "finding"]
    items: tuple[dict[str, Any], ...]
    page: int
    page_size: int
    total: int
    filters: dict[str, object]

    @property
    def page_count(self) -> int:
        return max(1, ceil(self.total / self.page_size))

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total


def _validate_page(page: int) -> None:
    if page < 1:
        raise DomainError("CATALOG_QUERY_INVALID", "page must be a positive integer")


def _validate_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(tag.strip() for tag in tags)
    if any(not tag for tag in normalized) or len(normalized) != len(set(normalized)):
        raise DomainError("CATALOG_QUERY_INVALID", "tags must be non-empty and unique")
    return normalized


def _page(
    kind: Literal["source", "note", "finding"],
    values: list[dict[str, Any]],
    page: int,
    filters: dict[str, object],
) -> CatalogPage:
    _validate_page(page)
    start = (page - 1) * CATALOG_PAGE_SIZE
    return CatalogPage(
        kind=kind,
        items=tuple(values[start : start + CATALOG_PAGE_SIZE]),
        page=page,
        page_size=CATALOG_PAGE_SIZE,
        total=len(values),
        filters=filters,
    )


def _catalog_item(source_or_note: Source | Note) -> dict[str, Any]:
    item: dict[str, Any] = {
        "object_id": str(source_or_note.id),
        "title": source_or_note.title,
        "visibility": source_or_note.visibility.value,
        "record_status": source_or_note.record_status.value,
        "created": source_or_note.created.isoformat(),
        "updated": source_or_note.updated.isoformat(),
        "tags": list(source_or_note.tags),
    }
    if isinstance(source_or_note, Source):
        item.update(
            kind="source",
            subtype=source_or_note.source_type.value,
            workflow_stage=source_or_note.workflow_stage.value,
        )
    else:
        item.update(
            kind="note",
            subtype=source_or_note.note_type.value,
            maturity=source_or_note.maturity.value,
        )
    return item


def _sorted_objects[T: Source | Note](values: list[T]) -> list[T]:
    values.sort(key=lambda value: str(value.id))
    values.sort(key=lambda value: value.updated, reverse=True)
    return values


class CatalogQueryService:
    """Read-only scanner-backed catalog shared by human interfaces."""

    def __init__(
        self,
        *,
        scanner: Callable[[Vault], ScanResult] = scan_vault,
        index_status: IndexStatusReader,
    ) -> None:
        self._scanner = scanner
        self._index_status = index_status

    def _snapshot(self, vault: Vault) -> ScanResult:
        return self._scanner(vault)

    def dashboard(self, vault: Vault) -> dict[str, Any]:
        scan = self._snapshot(vault)
        sources = _sorted_objects(
            [
                scanned.document.object
                for scanned in scan.objects.values()
                if isinstance(scanned.document.object, Source)
            ]
        )
        notes = _sorted_objects(
            [
                scanned.document.object
                for scanned in scan.objects.values()
                if isinstance(scanned.document.object, Note)
            ]
        )
        artifacts = [
            scanned.document.object
            for scanned in scan.objects.values()
            if isinstance(scanned.document.object, AIArtifact)
        ]
        visibility = {value.value: 0 for value in Visibility}
        for scanned in scan.objects.values():
            visibility[scanned.document.object.visibility.value] += 1
        return {
            "object_counts": scan.object_counts(),
            "visibility_counts": visibility,
            "source_type_counts": {
                value.value: sum(source.source_type is value for source in sources)
                for value in SourceType
            },
            "note_type_counts": {
                value.value: sum(note.note_type is value for note in notes) for value in NoteType
            },
            "workflow_counts": {
                value.value: sum(source.workflow_stage is value for source in sources)
                for value in WorkflowStage
            },
            "review_counts": {
                value.value: sum(artifact.review_status is value for artifact in artifacts)
                for value in ReviewStatus
            },
            "finding_counts": {
                severity: sum(finding.severity == severity for finding in scan.findings)
                for severity in ("error", "warning")
            },
            "index": self._index_status(vault, scan),
            "recent_sources": tuple(_catalog_item(source) for source in sources[:5]),
            "recent_notes": tuple(_catalog_item(note) for note in notes[:5]),
        }

    def sources(
        self,
        vault: Vault,
        *,
        source_type: str | None = None,
        workflow_stage: str | None = None,
        record_status: str | None = None,
        visibility: str | None = None,
        tags: tuple[str, ...] = (),
        page: int = 1,
    ) -> CatalogPage:
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
        selected_tags = _validate_tags(tags)
        scan = self._snapshot(vault)
        values = [
            scanned.document.object
            for scanned in scan.objects.values()
            if isinstance(scanned.document.object, Source)
        ]
        values = [
            value
            for value in values
            if (type_value is None or value.source_type is type_value)
            and (stage_value is None or value.workflow_stage is stage_value)
            and (status_value is None or value.record_status is status_value)
            and (visibility_value is None or value.visibility is visibility_value)
            and all(tag in value.tags for tag in selected_tags)
        ]
        filters: dict[str, object] = {
            "source_type": type_value.value if type_value else None,
            "workflow_stage": stage_value.value if stage_value else None,
            "record_status": status_value.value if status_value else None,
            "visibility": visibility_value.value if visibility_value else None,
            "tags": list(selected_tags),
        }
        return _page(
            "source", [_catalog_item(value) for value in _sorted_objects(values)], page, filters
        )

    def notes(
        self,
        vault: Vault,
        *,
        note_type: str | None = None,
        maturity: str | None = None,
        record_status: str | None = None,
        visibility: str | None = None,
        tags: tuple[str, ...] = (),
        page: int = 1,
    ) -> CatalogPage:
        type_value = enum_value(NoteType, note_type, field="Note type") if note_type else None
        maturity_value = enum_value(Maturity, maturity, field="maturity") if maturity else None
        status_value = (
            enum_value(RecordStatus, record_status, field="record status")
            if record_status
            else None
        )
        visibility_value = (
            enum_value(Visibility, visibility, field="visibility") if visibility else None
        )
        selected_tags = _validate_tags(tags)
        scan = self._snapshot(vault)
        values = [
            scanned.document.object
            for scanned in scan.objects.values()
            if isinstance(scanned.document.object, Note)
        ]
        values = [
            value
            for value in values
            if (type_value is None or value.note_type is type_value)
            and (maturity_value is None or value.maturity is maturity_value)
            and (status_value is None or value.record_status is status_value)
            and (visibility_value is None or value.visibility is visibility_value)
            and all(tag in value.tags for tag in selected_tags)
        ]
        filters: dict[str, object] = {
            "note_type": type_value.value if type_value else None,
            "maturity": maturity_value.value if maturity_value else None,
            "record_status": status_value.value if status_value else None,
            "visibility": visibility_value.value if visibility_value else None,
            "tags": list(selected_tags),
        }
        return _page(
            "note", [_catalog_item(value) for value in _sorted_objects(values)], page, filters
        )

    def detail(
        self,
        vault: Vault,
        object_id: str,
        *,
        expected_kind: Literal["source", "note"],
    ) -> dict[str, object]:
        scan = self._snapshot(vault)
        try:
            parsed_id = ObjectId(object_id)
        except DomainError as error:
            raise DomainError("OBJECT_NOT_FOUND", "object ID was not found") from error
        if parsed_id.kind.value != expected_kind:
            raise DomainError("OBJECT_NOT_FOUND", "object ID was not found")
        result = get_object(vault, object_id, scan=scan)
        if cast(dict[str, object], result["object"])["kind"] != expected_kind:
            raise DomainError("OBJECT_NOT_FOUND", "object ID was not found")
        return result

    def health(self, vault: Vault, *, page: int = 1) -> dict[str, object]:
        scan = self._snapshot(vault)
        findings = [finding.as_dict() for finding in sorted(scan.findings)]
        return {
            "healthy": scan.healthy,
            "files_scanned": scan.files_scanned,
            "object_counts": scan.object_counts(),
            "index": self._index_status(vault, scan),
            "findings": _page("finding", findings, page, {}),
        }
