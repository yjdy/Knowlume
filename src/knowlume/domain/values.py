from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Self


class DomainError(ValueError):
    """A stable Contract v2 parse or domain validation failure."""

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


@dataclass(frozen=True, order=True)
class ObjectId:
    value: str

    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<prefix>src|note|snip|ai)_[0-9A-HJKMNP-TV-Z]{26}$"
    )
    _KINDS: ClassVar[dict[str, ObjectKind]] = {
        "src": ObjectKind.SOURCE,
        "note": ObjectKind.NOTE,
        "snip": ObjectKind.SNIPPET,
        "ai": ObjectKind.AI_ARTIFACT,
    }

    @classmethod
    def parse(cls, value: object, *, expected_kind: ObjectKind | None = None) -> Self:
        if not isinstance(value, str):
            raise DomainError("OBJECT_ID_INVALID", "object ID must be a string")
        match = cls._PATTERN.fullmatch(value)
        if match is None:
            raise DomainError("OBJECT_ID_INVALID", f"invalid object ID: {value!r}")
        result = cls(value)
        if expected_kind is not None and result.kind is not expected_kind:
            raise DomainError(
                "OBJECT_KIND_MISMATCH",
                f"object ID {value!r} does not identify {expected_kind.value}",
            )
        return result

    @property
    def kind(self) -> ObjectKind:
        prefix = self.value.split("_", 1)[0]
        return self._KINDS[prefix]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SectionId:
    value: str

    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^sec_[a-z0-9][a-z0-9_-]{2,63}$")

    @classmethod
    def parse(cls, value: object) -> Self:
        if not isinstance(value, str) or cls._PATTERN.fullmatch(value) is None:
            raise DomainError("SECTION_ID_INVALID", f"invalid section ID: {value!r}")
        return cls(value)

    def __str__(self) -> str:
        return self.value


def enum_value(enum_type: type[StrEnum], value: object, *, field: str) -> StrEnum:
    if not isinstance(value, str):
        raise DomainError("FIELD_INVALID", f"{field} must be a string")
    try:
        return enum_type(value)
    except ValueError as error:
        raise DomainError("FIELD_INVALID", f"unsupported {field}: {value!r}") from error
