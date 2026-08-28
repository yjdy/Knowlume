from __future__ import annotations

from collections.abc import Iterable

from knowlume.domain.models import Source
from knowlume.domain.paper import PaperIdentity, normalize_arxiv, normalize_doi
from knowlume.domain.values import DomainError, ObjectId, SourceType


def source_identity(source: Source) -> PaperIdentity | None:
    if source.source_type is not SourceType.PAPER:
        return None
    doi = normalize_doi(source.doi) if source.doi else None
    arxiv = (
        normalize_arxiv(
            f"{source.arxiv_id}v{source.arxiv_version}"
            if source.arxiv_id and source.arxiv_version
            else source.arxiv_id
        )
        if source.arxiv_id
        else None
    )
    return PaperIdentity(doi, arxiv) if doi or arxiv else None


def find_existing_paper(sources: Iterable[Source], identity: PaperIdentity) -> ObjectId | None:
    matches: dict[str, ObjectId] = {}
    wanted = set(identity.aliases)
    for source in sources:
        current = source_identity(source)
        if current is None:
            continue
        overlap = wanted.intersection(current.aliases)
        for alias in overlap:
            matches[alias] = source.id
    ids = set(matches.values())
    if len(ids) > 1:
        raise DomainError(
            "PAPER_IDENTITY_CONFLICT",
            "DOI and arXiv identifiers resolve to different Sources",
            details={"matches": {key: str(value) for key, value in sorted(matches.items())}},
        )
    return next(iter(ids)) if ids else None
