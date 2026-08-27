from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from knowlume.domain.values import (
    ActorType,
    ArtifactType,
    DomainError,
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


def _required(value: str, field: str) -> None:
    if not value.strip():
        raise DomainError("FIELD_INVALID", f"{field} must be a non-empty string")


@dataclass(frozen=True)
class Actor:
    type: ActorType
    id: str

    def __post_init__(self) -> None:
        _required(self.id, "actor.id")


@dataclass(frozen=True)
class SnapshotRef:
    provider: str
    identifier: str
    captured_at: datetime
    content_hash: str

    def __post_init__(self) -> None:
        if not self.provider or not self.identifier or not self.content_hash.startswith("sha256:"):
            raise DomainError("SNAPSHOT_INVALID", "snapshot reference is incomplete")


@dataclass(frozen=True)
class PaperLocator:
    page: int | None = None
    page_label: str | None = None
    section: str | None = None
    figure: str | None = None
    table: str | None = None

    def __post_init__(self) -> None:
        if not any((self.page, self.page_label, self.section, self.figure, self.table)):
            raise DomainError("LOCATOR_INVALID", "paper locator needs a position")
        if self.page is not None and self.page < 1:
            raise DomainError("LOCATOR_INVALID", "paper page must be positive")


@dataclass(frozen=True)
class WebLocator:
    snapshot_ref: SnapshotRef
    heading_path: tuple[str, ...] = ()
    paragraph: int | None = None

    def __post_init__(self) -> None:
        if not self.heading_path and self.paragraph is None:
            raise DomainError("LOCATOR_INVALID", "web locator needs a heading path or paragraph")
        if self.paragraph is not None and self.paragraph < 1:
            raise DomainError("LOCATOR_INVALID", "web paragraph must be positive")


@dataclass(frozen=True)
class BookLocator:
    edition: str | None = None
    isbn: str | None = None
    chapter: str | None = None
    page: int | None = None
    location: str | None = None

    def __post_init__(self) -> None:
        if not any((self.chapter, self.page, self.location)):
            raise DomainError("LOCATOR_INVALID", "book locator needs a position")
        if self.page is not None and not (self.edition or self.isbn):
            raise DomainError("LOCATOR_INVALID", "book page locator needs edition or ISBN")


@dataclass(frozen=True)
class OssLocator:
    repository_host: str
    repository_path: str
    commit: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol and (self.start_line is None or self.end_line is None):
            raise DomainError("LOCATOR_INVALID", "OSS locator needs a line range or symbol")
        if (
            self.start_line is not None
            and self.end_line is not None
            and (self.start_line < 1 or self.end_line < self.start_line)
        ):
            raise DomainError("LOCATOR_INVALID", "OSS line range is invalid")


type Locator = PaperLocator | WebLocator | BookLocator | OssLocator


@dataclass(frozen=True)
class Citation:
    source_id: ObjectId
    locator: Locator

    def __post_init__(self) -> None:
        if self.source_id.kind.value != "source":
            raise DomainError("CITATION_SOURCE_INVALID", "citation target must be a Source")


@dataclass(frozen=True)
class HumanBlock:
    text: str


@dataclass(frozen=True)
class FactBlock:
    text: str
    citations: tuple[Citation, ...]

    def __post_init__(self) -> None:
        if not self.text or not self.citations:
            raise DomainError("FACT_CITATION_MISSING", "Fact block requires text and citations")


@dataclass(frozen=True)
class AIBlock:
    text: str
    artifact_id: ObjectId

    def __post_init__(self) -> None:
        if not self.text or self.artifact_id.kind.value != "ai_artifact":
            raise DomainError("AI_ARTIFACT_INVALID", "AI block must reference an AI Artifact")


type SectionBlock = HumanBlock | FactBlock | AIBlock


@dataclass(frozen=True)
class NoteSection:
    section_id: SectionId
    role: SectionRole
    heading: str
    blocks: tuple[SectionBlock, ...]

    def __post_init__(self) -> None:
        allowed = {
            SectionRole.HUMAN: HumanBlock,
            SectionRole.EVOLUTION: HumanBlock,
            SectionRole.FACT: FactBlock,
            SectionRole.AI: AIBlock,
        }[self.role]
        if not self.heading or any(not isinstance(block, allowed) for block in self.blocks):
            raise DomainError("NOTE_BLOCK_ROLE_MISMATCH", "block kind does not match section role")


@dataclass(frozen=True)
class NoteBody:
    note_id: ObjectId
    sections: tuple[NoteSection, ...]

    def __post_init__(self) -> None:
        ids = [section.section_id for section in self.sections]
        if len(ids) != len(set(ids)):
            duplicate = next(str(item) for item in ids if ids.count(item) > 1)
            raise DomainError("SECTION_ID_DUPLICATE", f"duplicate section ID: {duplicate}")
        if not any(section.role is SectionRole.HUMAN for section in self.sections):
            raise DomainError(
                "NOTE_HUMAN_SECTION_MISSING", "Note requires at least one human section"
            )


@dataclass(frozen=True)
class TypeTransition:
    from_type: NoteType
    to_type: NoteType
    changed_at: datetime
    actor: Actor

    def __post_init__(self) -> None:
        if (self.from_type, self.to_type) != (NoteType.IDEA, NoteType.CONCEPT):
            raise DomainError("NOTE_TRANSITION_INVALID", "only Idea-to-Concept is supported")


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

    def __post_init__(self) -> None:
        if self.id.kind.value != "source" or not self.title:
            raise DomainError("OBJECT_KIND_MISMATCH", "Source identity is invalid")
        identities = {
            SourceType.PAPER: bool(self.canonical_url or self.doi or self.zotero_key),
            SourceType.WEB: bool(self.canonical_url and self.captured_at),
            SourceType.BOOK: bool(self.isbn or self.doi or self.zotero_key or self.canonical_url),
            SourceType.OSS: all(
                (
                    self.canonical_url,
                    self.repository_host,
                    self.repository_path,
                    self.commit,
                    self.license,
                )
            ),
        }
        if not identities[self.source_type]:
            raise DomainError(
                "SOURCE_IDENTITY_MISSING", f"{self.source_type.value} Source metadata is incomplete"
            )


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

    def __post_init__(self) -> None:
        if self.id.kind.value != "note" or not self.title:
            raise DomainError("OBJECT_KIND_MISMATCH", "Note identity is invalid")
        if self.note_type is NoteType.IDEA and self.maturity not in {
            Maturity.SEED,
            Maturity.DEVELOPING,
        }:
            raise DomainError("NOTE_MATURITY_INVALID", "Idea maturity must be seed or developing")
        if (
            self.note_type in {NoteType.IDEA, NoteType.LITERATURE, NoteType.SYNTHESIS}
            and self.type_history
        ):
            raise DomainError("NOTE_TRANSITION_INVALID", "Note type cannot have type history")
        if len(self.type_history) > 1:
            raise DomainError("NOTE_TRANSITION_INVALID", "Concept has too many type transitions")


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

    def __post_init__(self) -> None:
        if self.id.kind.value != "snippet" or self.source_id.kind.value != "source":
            raise DomainError("OBJECT_KIND_MISMATCH", "Snippet identity is invalid")
        if self.start_line < 1 or self.end_line < self.start_line:
            raise DomainError("SNIPPET_RANGE_INVALID", "Snippet line range is reversed")


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

    def __post_init__(self) -> None:
        if self.id.kind.value != "ai_artifact" or self.visibility is not Visibility.PRIVATE:
            raise DomainError(
                "AI_ARTIFACT_INVALID", "AI Artifact identity or visibility is invalid"
            )
        reviewed = self.review_status is not ReviewStatus.UNREVIEWED
        if reviewed != bool(self.reviewed_by and self.reviewed_at):
            raise DomainError(
                "AI_REVIEW_INVALID", "AI review provenance does not match review status"
            )


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

    @property
    def canonical_key(self) -> tuple[str, str, str, str]:
        return (
            str(self.to_id),
            str(self.to_section_id or ""),
            self.relation_type.value,
            repr(self.locator),
        )


@dataclass(frozen=True)
class RelationShard:
    from_id: ObjectId
    relations: tuple[Relation, ...]
