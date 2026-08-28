from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DomainError(ValueError):
    """Stable typed Contract v2 failure."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ObjectKind(StrEnum):
    SOURCE = "source"
    NOTE = "note"
    SNIPPET = "snippet"
    AI_ARTIFACT = "ai_artifact"


class SourceType(StrEnum):
    PAPER = "paper"
    WEB = "web"
    BOOK = "book"
    OSS = "oss"


class Visibility(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"


class RecordStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class WorkflowStage(StrEnum):
    INBOX = "inbox"
    READING = "reading"
    PROCESSED = "processed"
    INTEGRATED = "integrated"


class NoteType(StrEnum):
    IDEA = "idea"
    LITERATURE = "literature"
    CONCEPT = "concept"
    SYNTHESIS = "synthesis"


class Maturity(StrEnum):
    SEED = "seed"
    DEVELOPING = "developing"
    MATURE = "mature"
    EVERGREEN = "evergreen"


class ArtifactType(StrEnum):
    SUMMARY = "summary"
    EXTRACTION = "extraction"
    RELATION_CANDIDATE = "relation_candidate"
    DRAFT = "draft"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROMOTED = "promoted"


class SectionRole(StrEnum):
    HUMAN = "human"
    FACT = "fact"
    AI = "ai"
    EVOLUTION = "evolution"


class ActorType(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"


class RelationType(StrEnum):
    CITES = "cites"
    DERIVED_FROM = "derived_from"
    SUMMARIZES = "summarizes"
    SYNTHESIZES = "synthesizes"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    RELATED_TO = "related_to"
    SNIPPET_FROM = "snippet_from"
    PROMOTED_FROM = "promoted_from"
    SUPERSEDES = "supersedes"


_ID_RE = re.compile(r"^(src|note|snip|ai)_[0-9A-HJKMNP-TV-Z]{26}$")
_SECTION_RE = re.compile(r"^sec_[a-z0-9][a-z0-9_-]{2,63}$")
_KIND_BY_PREFIX = {
    "src": ObjectKind.SOURCE,
    "note": ObjectKind.NOTE,
    "snip": ObjectKind.SNIPPET,
    "ai": ObjectKind.AI_ARTIFACT,
}


@dataclass(frozen=True, order=True)
class ObjectId:
    value: str

    def __post_init__(self) -> None:
        if not _ID_RE.fullmatch(self.value):
            raise DomainError("OBJECT_ID_INVALID", f"invalid object ID: {self.value!r}")

    @property
    def kind(self) -> ObjectKind:
        match = _ID_RE.fullmatch(self.value)
        assert match is not None
        return _KIND_BY_PREFIX[match.group(1)]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SectionId:
    value: str

    def __post_init__(self) -> None:
        if not _SECTION_RE.fullmatch(self.value):
            raise DomainError("SECTION_ID_INVALID", f"invalid section ID: {self.value!r}")

    def __str__(self) -> str:
        return self.value


def enum_value[EnumT: StrEnum](enum_type: type[EnumT], value: object, *, field: str) -> EnumT:
    try:
        return enum_type(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise DomainError("FIELD_INVALID", f"unsupported {field}: {value!r}") from error
