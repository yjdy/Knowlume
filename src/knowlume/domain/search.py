from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from knowlume.domain.models import Citation
from knowlume.domain.values import DomainError


class ContextScope(StrEnum):
    TRUSTED_LOCAL = "trusted-local"
    PUBLIC_SAFE = "public-safe"


class IndexState(StrEnum):
    MISSING = "missing"
    FRESH = "fresh"
    STALE = "stale"
    INCOMPATIBLE = "incompatible"
    CORRUPT = "corrupt"


SEARCH_ROLES = ("source", "human", "fact", "ai", "evolution", "snippet")
SEARCH_KINDS = ("source", "note", "snippet", "ai_artifact")


@dataclass(frozen=True)
class SearchFilters:
    kind: str | None = None
    subtype: str | None = None
    visibility: str | None = None
    record_status: str | None = None
    workflow_stage: str | None = None
    maturity: str | None = None
    review_status: str | None = None
    tags: tuple[str, ...] = ()
    role: str | None = None

    def __post_init__(self) -> None:
        allowed: dict[str, set[str]] = {
            "kind": set(SEARCH_KINDS),
            "subtype": {
                "paper",
                "web",
                "book",
                "oss",
                "idea",
                "literature",
                "concept",
                "synthesis",
                "summary",
                "extraction",
                "relation_candidate",
                "draft",
            },
            "visibility": {"private", "public"},
            "record_status": {"active", "archived", "superseded"},
            "workflow_stage": {"inbox", "reading", "processed", "integrated"},
            "maturity": {"seed", "developing", "mature", "evergreen"},
            "review_status": {"unreviewed", "accepted", "rejected", "promoted"},
            "role": set(SEARCH_ROLES),
        }
        for name, choices in allowed.items():
            value = getattr(self, name)
            if value is not None and value not in choices:
                raise DomainError(
                    "SEARCH_QUERY_INVALID", f"unsupported {name.replace('_', '-')} filter"
                )
        if any(not tag.strip() for tag in self.tags) or len(self.tags) != len(set(self.tags)):
            raise DomainError("SEARCH_QUERY_INVALID", "tags must be non-empty and unique")

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "subtype": self.subtype,
            "visibility": self.visibility,
            "record_status": self.record_status,
            "workflow_stage": self.workflow_stage,
            "maturity": self.maturity,
            "review_status": self.review_status,
            "tags": list(self.tags),
            "role": self.role,
        }


@dataclass(frozen=True)
class ProjectionSegment:
    segment_id: str
    object_id: str
    section_id: str | None
    role: str
    text: str
    ordinal: int
    citations: tuple[Citation, ...] = ()
    ai_artifact_id: str | None = None


@dataclass(frozen=True)
class SearchHit:
    segment_id: str
    object_id: str
    kind: str
    subtype: str | None
    path: str
    title: str
    section_id: str | None
    role: str
    ordinal: int
    text: str
    score: float
    tags: tuple[str, ...]
    visibility: str
    record_status: str
    citations: tuple[dict[str, object], ...]


HAN_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EBEF),
    (0x2EBF0, 0x2EE5F),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x3134F),
    (0x31350, 0x323AF),
    (0x323B0, 0x3347F),
)


def is_han(character: str) -> bool:
    value = ord(character)
    return any(start <= value <= end for start, end in HAN_RANGES)


def tokenize(text: str) -> tuple[str, ...]:
    """Apply the frozen tokenizer-v1 normalization and ordering."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    ordinary: list[str] = []
    han: list[str] = []

    def flush_ordinary() -> None:
        if ordinary:
            tokens.append("".join(ordinary))
            ordinary.clear()

    def flush_han() -> None:
        if han:
            tokens.extend(han)
            tokens.extend(han[index] + han[index + 1] for index in range(len(han) - 1))
            han.clear()

    for character in normalized:
        if is_han(character):
            flush_ordinary()
            han.append(character)
        elif unicodedata.category(character)[0] in {"L", "N"}:
            flush_han()
            ordinary.append(character)
        else:
            flush_ordinary()
            flush_han()
    flush_ordinary()
    flush_han()
    return tuple(tokens)


def literal_fts_query(text: str) -> str:
    terms = tokenize(text)
    if not terms:
        raise DomainError("SEARCH_QUERY_INVALID", "query must contain a letter or number term")
    return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


def segment_id(object_id: str, section_key: str, block_ordinal: int) -> str:
    material = f"segment-v1\0{object_id}\0{section_key}\0{block_ordinal}".encode()
    return "seg_" + hashlib.sha256(material).hexdigest()
