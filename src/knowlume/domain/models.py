from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from knowlume.domain.values import (
    ActorType,
    ArtifactType,
    Maturity,
    NoteType,
    ObjectId,
    RecordStatus,
    RelationType,
    ReviewStatus,
    SectionId,
    SectionRole,
    SourceType,
    Visibility,
    WorkflowStage,
)


@dataclass(frozen=True)
class Actor:
    type: ActorType
    id: str


@dataclass(frozen=True)
class SnapshotRef:
    provider: str
    identifier: str
    captured_at: datetime
    content_hash: str


@dataclass(frozen=True)
class PaperLocator:
    page: int | None = None
    page_label: str | None = None
    section: str | None = None
    figure: str | None = None
    table: str | None = None


@dataclass(frozen=True)
class WebLocator:
    snapshot_ref: SnapshotRef
    heading_path: tuple[str, ...] = ()
    paragraph: int | None = None


@dataclass(frozen=True)
class BookLocator:
    edition: str | None = None
    isbn: str | None = None
    chapter: str | None = None
    page: int | None = None
    location: str | None = None


@dataclass(frozen=True)
class OssLocator:
    repository_host: str
    repository_path: str
    commit: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None


type Locator = PaperLocator | WebLocator | BookLocator | OssLocator


@dataclass(frozen=True)
class Citation:
    source_id: ObjectId
    locator: Locator


@dataclass(frozen=True)
class HumanBlock:
    text: str


@dataclass(frozen=True)
class FactBlock:
    text: str
    citations: tuple[Citation, ...]


@dataclass(frozen=True)
class AIBlock:
    text: str
    artifact_id: ObjectId


type SectionBlock = HumanBlock | FactBlock | AIBlock


@dataclass(frozen=True)
class NoteSection:
    section_id: SectionId
    role: SectionRole
    heading: str
    blocks: tuple[SectionBlock, ...]


@dataclass(frozen=True)
class NoteBody:
    note_id: ObjectId
    sections: tuple[NoteSection, ...]


@dataclass(frozen=True)
class TypeTransition:
    from_type: NoteType
    to_type: NoteType
    changed_at: datetime
    actor: Actor


@dataclass(frozen=True)
class Source:
    id: ObjectId
    source_type: SourceType
    title: str
    visibility: Visibility
    record_status: RecordStatus
    workflow_stage: WorkflowStage
    created: date
    updated: date
    tags: tuple[str, ...]
    captured_at: datetime | None = None
    canonical_url: str | None = None
    snapshot_ref: SnapshotRef | None = None
    zotero_library_id: str | None = None
    zotero_key: str | None = None
    attachment_key: str | None = None
    isbn: str | None = None
    doi: str | None = None
    repository_host: str | None = None
    repository_path: str | None = None
    default_branch: str | None = None
    commit: str | None = None
    license: str | None = None
    year: int | None = None
    authors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Note:
    id: ObjectId
    note_type: NoteType
    title: str
    visibility: Visibility
    record_status: RecordStatus
    maturity: Maturity
    created: date
    updated: date
    tags: tuple[str, ...]
    type_history: tuple[TypeTransition, ...]


@dataclass(frozen=True)
class Snippet:
    id: ObjectId
    title: str
    source_id: ObjectId
    repository_host: str
    repository_path: str
    commit: str
    path: str
    start_line: int
    end_line: int
    license: str
    publication_approved: bool
    visibility: Visibility
    record_status: RecordStatus
    created: date
    updated: date
    tags: tuple[str, ...]


@dataclass(frozen=True)
class InputRef:
    object_id: ObjectId
    section_id: SectionId | None = None


@dataclass(frozen=True)
class AIArtifact:
    id: ObjectId
    artifact_type: ArtifactType
    title: str
    visibility: Visibility
    record_status: RecordStatus
    review_status: ReviewStatus
    created: date
    input_refs: tuple[InputRef, ...]
    generated_by: str
    model: str
    prompt_ref: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None


type DurableObject = Source | Note | Snippet | AIArtifact


@dataclass(frozen=True)
class ObjectDocument:
    object: DurableObject
    body: str | NoteBody


@dataclass(frozen=True)
class Relation:
    to_id: ObjectId
    relation_type: RelationType
    created_at: datetime
    actor: Actor
    to_section_id: SectionId | None = None
    locator: Locator | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RelationShard:
    from_id: ObjectId
    relations: tuple[Relation, ...]
