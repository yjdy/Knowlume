from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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


class ZoteroPort(Protocol):
    def metadata(self, reference: ZoteroReference) -> PaperMetadata: ...

    def primary_attachment(self, reference: ZoteroReference) -> AttachmentSelection: ...

    def attachment(self, reference: ZoteroReference, attachment_key: str) -> PrimaryAttachment: ...
