from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from knowlume.domain.models import SnapshotRef
from knowlume.domain.paper import ArxivIdentity, Doi, PaperIdentity


@dataclass(frozen=True)
class ZoteroReference:
    library_type: str
    library_id: str
    item_key: str


@dataclass(frozen=True)
class PaperMetadata:
    title: str
    authors: tuple[str, ...]
    year: int | None
    identity: PaperIdentity | None
    canonical_url: str | None
    zotero: ZoteroReference
    item_version: int

    @property
    def doi(self) -> Doi | None:
        return self.identity.doi if self.identity else None

    @property
    def arxiv(self) -> ArxivIdentity | None:
        return self.identity.arxiv if self.identity else None


@dataclass(frozen=True)
class PrimaryAttachment:
    key: str
    version: int
    filename: str
    media_type: str
    size: int
    sha256: str
    cache_path: Path


@dataclass(frozen=True)
class AttachmentSelection:
    attachment: PrimaryAttachment | None
    warning_code: str | None = None


@dataclass(frozen=True)
class ZoteroItem:
    reference: ZoteroReference
    item_type: str | None
    title: str
    authors: tuple[str, ...]
    year: int | None
    doi: Doi | None
    arxiv: ArxivIdentity | None
    isbn: str | None
    edition: str | None
    canonical_url: str | None
    item_version: int

    @property
    def paper_identity(self) -> PaperIdentity | None:
        return PaperIdentity(self.doi, self.arxiv) if self.doi or self.arxiv else None


@dataclass(frozen=True)
class WebSnapshotMetadata:
    reference: ZoteroReference
    title: str
    canonical_url: str
    item_version: int
    captured_at: datetime
    snapshot_ref: SnapshotRef


class ZoteroPort(Protocol):
    def metadata(self, reference: ZoteroReference) -> PaperMetadata: ...

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection: ...

    def attachment(self, reference: ZoteroReference, attachment_key: str) -> PrimaryAttachment: ...


class ZoteroCapturePort(ZoteroPort, Protocol):
    def exact_candidates(self, kind: str, value: str) -> tuple[ZoteroItem, ...]: ...

    def web_snapshot(self, item: ZoteroItem) -> WebSnapshotMetadata: ...
