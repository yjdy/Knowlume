from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from knowlume.domain.paper import ArxivIdentity, Doi
from knowlume.ports.zotero import PaperMetadata, ZoteroReference


@dataclass(frozen=True)
class PaperCaptureRequest:
    raw_input: str
    doi: Doi | None = None
    arxiv: ArxivIdentity | None = None
    zotero: ZoteroReference | None = None


class PaperMetadataPort(Protocol):
    def resolve(self, request: PaperCaptureRequest) -> PaperMetadata: ...
