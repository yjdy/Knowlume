from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from knowlume.domain.values import DomainError, ObjectId, SectionId

CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def evidence_error(message: str) -> DomainError:
    return DomainError("AI_REVIEW_EVIDENCE_INVALID", message)


def safe_evidence_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or any(ord(char) < 32 for char in value)
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
        or value == "."
    ):
        raise DomainError("VAULT_PATH_UNSAFE", "AI reference path is not safely Vault-relative")
    return value


def valid_checksum(value: str) -> None:
    if not CHECKSUM_RE.fullmatch(value):
        raise evidence_error("invalid evidence checksum")


def human_identity(value: str) -> str:
    if not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise evidence_error("human attribution must be non-empty canonical text")
    return value


def aware_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise evidence_error("evidence time must include a timezone")


@dataclass(frozen=True)
class FileRevision:
    path: str
    checksum: str | None

    def __post_init__(self) -> None:
        safe_evidence_path(self.path)
        if self.checksum is not None:
            valid_checksum(self.checksum)


@dataclass(frozen=True)
class ReviewAttribution:
    reviewed_by: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        human_identity(self.reviewed_by)
        aware_time(self.reviewed_at)


@dataclass(frozen=True)
class ReviewEvidence:
    version: int
    content_checksum: str
    decision: str
    reviewed_by: str
    reviewed_at: datetime
    dependencies: tuple[FileRevision, ...]
    prior_review: ReviewAttribution | None = None

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version != 1:
            raise DomainError(
                "AI_REVIEW_EVIDENCE_UNSUPPORTED", "unsupported review evidence version"
            )
        valid_checksum(self.content_checksum)
        human_identity(self.reviewed_by)
        aware_time(self.reviewed_at)
        if self.decision not in {"accepted", "rejected"}:
            raise evidence_error("invalid review evidence decision")
        if len({item.path for item in self.dependencies}) != len(self.dependencies):
            raise evidence_error("duplicate evidence dependency path")


@dataclass(frozen=True)
class PromotionEvidence:
    version: int
    note_id: ObjectId
    section_id: SectionId
    actor_id: str
    promoted_at: datetime
    note_checksum: str
    relation_checksum: str

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version != 1:
            raise DomainError(
                "AI_REVIEW_EVIDENCE_UNSUPPORTED", "unsupported promotion evidence version"
            )
        if self.note_id.kind.value != "note":
            raise evidence_error("promotion target must be a Note")
        human_identity(self.actor_id)
        aware_time(self.promoted_at)
        valid_checksum(self.note_checksum)
        valid_checksum(self.relation_checksum)
