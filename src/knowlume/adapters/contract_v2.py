from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from knowlume.constants import LOCATOR_VERSION, OBJECT_CONTRACT_VERSION, RELATION_SCHEMA_VERSION
from knowlume.domain.models import (
    Actor,
    AIArtifact,
    AIBlock,
    BookLocator,
    Citation,
    DurableObject,
    FactBlock,
    HumanBlock,
    InputRef,
    Locator,
    Note,
    NoteBody,
    NoteSection,
    ObjectDocument,
    OssLocator,
    PaperLocator,
    Relation,
    RelationShard,
    SnapshotRef,
    Snippet,
    Source,
    TypeTransition,
    WebLocator,
)
from knowlume.domain.values import (
    ActorType,
    ArtifactType,
    DomainError,
    Maturity,
    NoteType,
    ObjectId,
    ObjectKind,
    RecordStatus,
    RelationType,
    ReviewStatus,
    SectionId,
    SectionRole,
    SourceType,
    Visibility,
    WorkflowStage,
)

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
SECTION_RE = re.compile(
    r"^<!--\s*knowlume:section\s+id=(?P<id>sec_[a-z0-9][a-z0-9_-]{2,63})"
    r"\s+role=(?P<role>[a-z]+)\s*-->\r?\n"
    r"(?P<level>#{1,6})\s+(?P<heading>[^\r\n]+)(?:\r?\n|\Z)",
    re.MULTILINE,
)
FACT_BLOCK_RE = re.compile(
    r"<!--\s*knowlume:fact\r?\n(?P<meta>.*?)\r?\n-->\s*"
    r"(?P<text>.+?)(?=(?:\r?\n){2,}<!--\s*knowlume:fact|\Z)",
    re.DOTALL,
)
AI_BLOCK_RE = re.compile(
    r"<!--\s*knowlume:ai\r?\n(?P<meta>.*?)\r?\n-->\s*"
    r"(?P<text>.+?)(?=(?:\r?\n){2,}<!--\s*knowlume:ai|\Z)",
    re.DOTALL,
)
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
REPOSITORY_PATH_RE = re.compile(r"^[^/\s]+(?:/[^/\s]+)+$")


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DomainError("PARSE_INVALID", f"{field} must be a mapping")
    return cast(dict[str, Any], value)


def _sequence(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise DomainError("FIELD_INVALID", f"{field} must be an array")
    return value


def _exact_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    field: str,
) -> None:
    optional = optional or set()
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing:
        raise DomainError("FIELD_MISSING", f"{field} is missing: {', '.join(sorted(missing))}")
    if extra:
        raise DomainError(
            "FIELD_UNKNOWN", f"{field} has unknown fields: {', '.join(sorted(extra))}"
        )


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DomainError("FIELD_INVALID", f"{field} must be a non-empty string")
    return value


def _optional_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field=field)


def _integer(value: object, *, field: str, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DomainError("FIELD_INVALID", f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise DomainError("FIELD_INVALID", f"{field} must be at least {minimum}")
    return value


def _optional_integer(value: object, *, field: str, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    return _integer(value, field=field, minimum=minimum)


def _boolean(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise DomainError("FIELD_INVALID", f"{field} must be a boolean")
    return value


def _enum[E: StrEnum](enum_type: type[E], value: object, *, field: str) -> E:
    text = _string(value, field=field)
    try:
        return enum_type(text)
    except ValueError as error:
        raise DomainError("FIELD_INVALID", f"unsupported {field}: {text!r}") from error


def _date(value: object, *, field: str) -> date:
    text = _string(value, field=field)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise DomainError("FIELD_INVALID", f"{field} must be an ISO date") from error


def _datetime(value: object, *, field: str) -> datetime:
    text = _string(value, field=field)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise DomainError("FIELD_INVALID", f"{field} must be an ISO date-time") from error
    if result.tzinfo is None:
        raise DomainError("FIELD_INVALID", f"{field} must include a UTC offset")
    return result


def _optional_datetime(value: object, *, field: str) -> datetime | None:
    if value is None:
        return None
    return _datetime(value, field=field)


def _tags(value: object) -> tuple[str, ...]:
    tags = tuple(_string(item, field="tags item") for item in _sequence(value, field="tags"))
    if len(tags) != len(set(tags)) or any(TAG_RE.fullmatch(tag) is None for tag in tags):
        raise DomainError("FIELD_INVALID", "tags must be unique normalized tag values")
    return tags


def _strings(value: object, *, field: str, minimum: int = 0) -> tuple[str, ...]:
    result = tuple(_string(item, field=f"{field} item") for item in _sequence(value, field=field))
    if len(result) < minimum or len(result) != len(set(result)):
        raise DomainError("FIELD_INVALID", f"{field} has invalid cardinality or duplicates")
    return result


def _actor(value: object, *, field: str = "actor") -> Actor:
    data = _mapping(value, field=field)
    _exact_keys(data, required={"type", "id"}, field=field)
    return Actor(
        type=_enum(ActorType, data["type"], field=f"{field}.type"),
        id=_string(data["id"], field=f"{field}.id"),
    )


def _snapshot_ref(value: object, *, field: str = "snapshot_ref") -> SnapshotRef:
    data = _mapping(value, field=field)
    _exact_keys(
        data,
        required={"provider", "identifier", "captured_at", "content_hash"},
        field=field,
    )
    checksum = _string(data["content_hash"], field=f"{field}.content_hash")
    if CHECKSUM_RE.fullmatch(checksum) is None:
        raise DomainError("FIELD_INVALID", f"{field}.content_hash must be a SHA-256 checksum")
    return SnapshotRef(
        provider=_string(data["provider"], field=f"{field}.provider"),
        identifier=_string(data["identifier"], field=f"{field}.identifier"),
        captured_at=_datetime(data["captured_at"], field=f"{field}.captured_at"),
        content_hash=checksum,
    )


def parse_locator(value: object) -> Locator:
    data = _mapping(value, field="locator")
    if data.get("locator_version") != LOCATOR_VERSION:
        raise DomainError("LOCATOR_VERSION_UNSUPPORTED", "unsupported locator version")
    source_type = _enum(SourceType, data.get("source_type"), field="locator.source_type")
    common = {"locator_version", "source_type"}
    if source_type is SourceType.PAPER:
        optional = {"page", "page_label", "section", "figure", "table"}
        _exact_keys(data, required=common, optional=optional, field="paper locator")
        paper = PaperLocator(
            page=_optional_integer(data.get("page"), field="locator.page", minimum=1),
            page_label=_optional_string(data.get("page_label"), field="locator.page_label"),
            section=_optional_string(data.get("section"), field="locator.section"),
            figure=_optional_string(data.get("figure"), field="locator.figure"),
            table=_optional_string(data.get("table"), field="locator.table"),
        )
        if all(
            value is None
            for value in (paper.page, paper.page_label, paper.section, paper.figure, paper.table)
        ):
            raise DomainError("LOCATOR_INVALID", "paper locator has no precise position")
        return paper
    if source_type is SourceType.WEB:
        _exact_keys(
            data,
            required=common | {"snapshot_ref"},
            optional={"heading_path", "paragraph"},
            field="web locator",
        )
        heading_path: tuple[str, ...] = ()
        if "heading_path" in data:
            heading_path = _strings(data["heading_path"], field="locator.heading_path", minimum=1)
        paragraph = _optional_integer(data.get("paragraph"), field="locator.paragraph", minimum=1)
        if not heading_path and paragraph is None:
            raise DomainError("LOCATOR_INVALID", "web locator has no precise position")
        return WebLocator(
            snapshot_ref=_snapshot_ref(data["snapshot_ref"]),
            heading_path=heading_path,
            paragraph=paragraph,
        )
    if source_type is SourceType.BOOK:
        _exact_keys(
            data,
            required=common,
            optional={"edition", "isbn", "chapter", "page", "location"},
            field="book locator",
        )
        book = BookLocator(
            edition=_optional_string(data.get("edition"), field="locator.edition"),
            isbn=_optional_string(data.get("isbn"), field="locator.isbn"),
            chapter=_optional_string(data.get("chapter"), field="locator.chapter"),
            page=_optional_integer(data.get("page"), field="locator.page", minimum=1),
            location=_optional_string(data.get("location"), field="locator.location"),
        )
        if book.chapter is None and book.page is None and book.location is None:
            raise DomainError("LOCATOR_INVALID", "book locator has no precise position")
        if book.page is not None and book.edition is None and book.isbn is None:
            raise DomainError("LOCATOR_INVALID", "book page locator needs edition or ISBN")
        return book
    _exact_keys(
        data,
        required=common | {"repository_host", "repository_path", "commit", "path"},
        optional={"start_line", "end_line", "symbol"},
        field="OSS locator",
    )
    repository_path = _string(data["repository_path"], field="locator.repository_path")
    commit = _string(data["commit"], field="locator.commit")
    path = _string(data["path"], field="locator.path")
    if REPOSITORY_PATH_RE.fullmatch(repository_path) is None or COMMIT_RE.fullmatch(commit) is None:
        raise DomainError("LOCATOR_INVALID", "OSS locator repository identity is invalid")
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", path):
        raise DomainError("LOCATOR_INVALID", "OSS locator path must be relative")
    start_line = _optional_integer(data.get("start_line"), field="locator.start_line", minimum=1)
    end_line = _optional_integer(data.get("end_line"), field="locator.end_line", minimum=1)
    symbol = _optional_string(data.get("symbol"), field="locator.symbol")
    if (start_line is None) != (end_line is None) or (start_line is None and symbol is None):
        raise DomainError("LOCATOR_INVALID", "OSS locator needs a line range or symbol")
    if start_line is not None and end_line is not None and start_line > end_line:
        raise DomainError("LOCATOR_INVALID", "OSS locator line range is reversed")
    return OssLocator(
        repository_host=_string(data["repository_host"], field="locator.repository_host"),
        repository_path=repository_path,
        commit=commit,
        path=path,
        start_line=start_line,
        end_line=end_line,
        symbol=symbol,
    )


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise DomainError("FRONTMATTER_MISSING", "object document has no YAML frontmatter")
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        raise DomainError("FRONTMATTER_INVALID", "object frontmatter is not valid YAML") from error
    return _mapping(data, field="frontmatter"), text[match.end() :].strip()


def _base_object(
    data: dict[str, Any], kind: ObjectKind
) -> tuple[ObjectId, str, Visibility, RecordStatus]:
    if data.get("schema_version") != OBJECT_CONTRACT_VERSION:
        raise DomainError("OBJECT_VERSION_UNSUPPORTED", "unsupported object Contract version")
    actual_kind = _enum(ObjectKind, data.get("kind"), field="kind")
    if actual_kind is not kind:
        raise DomainError(
            "OBJECT_KIND_MISMATCH", f"expected {kind.value}, found {actual_kind.value}"
        )
    return (
        ObjectId.parse(data.get("id"), expected_kind=kind),
        _string(data.get("title"), field="title"),
        _enum(Visibility, data.get("visibility"), field="visibility"),
        _enum(RecordStatus, data.get("record_status"), field="record_status"),
    )


def _parse_source(data: dict[str, Any]) -> Source:
    required = {
        "schema_version",
        "id",
        "kind",
        "source_type",
        "title",
        "visibility",
        "record_status",
        "workflow_stage",
        "created",
        "updated",
        "tags",
    }
    optional = {
        "captured_at",
        "canonical_url",
        "snapshot_ref",
        "zotero_library_id",
        "zotero_key",
        "attachment_key",
        "isbn",
        "doi",
        "repository_host",
        "repository_path",
        "default_branch",
        "commit",
        "license",
        "year",
        "authors",
    }
    _exact_keys(data, required=required, optional=optional, field="Source")
    object_id, title, visibility, record_status = _base_object(data, ObjectKind.SOURCE)
    source_type = _enum(SourceType, data["source_type"], field="source_type")
    repository_path = _optional_string(data.get("repository_path"), field="repository_path")
    commit = _optional_string(data.get("commit"), field="commit")
    if repository_path is not None and REPOSITORY_PATH_RE.fullmatch(repository_path) is None:
        raise DomainError("FIELD_INVALID", "repository_path is invalid")
    if commit is not None and COMMIT_RE.fullmatch(commit) is None:
        raise DomainError("FIELD_INVALID", "commit must be a full immutable hash")
    source = Source(
        id=object_id,
        source_type=source_type,
        title=title,
        visibility=visibility,
        record_status=record_status,
        workflow_stage=_enum(WorkflowStage, data["workflow_stage"], field="workflow_stage"),
        created=_date(data["created"], field="created"),
        updated=_date(data["updated"], field="updated"),
        tags=_tags(data["tags"]),
        captured_at=_optional_datetime(data.get("captured_at"), field="captured_at"),
        canonical_url=_optional_string(data.get("canonical_url"), field="canonical_url"),
        snapshot_ref=_snapshot_ref(data["snapshot_ref"]) if "snapshot_ref" in data else None,
        zotero_library_id=_optional_string(
            data.get("zotero_library_id"), field="zotero_library_id"
        ),
        zotero_key=_optional_string(data.get("zotero_key"), field="zotero_key"),
        attachment_key=_optional_string(data.get("attachment_key"), field="attachment_key"),
        isbn=_optional_string(data.get("isbn"), field="isbn"),
        doi=_optional_string(data.get("doi"), field="doi"),
        repository_host=_optional_string(data.get("repository_host"), field="repository_host"),
        repository_path=repository_path,
        default_branch=_optional_string(data.get("default_branch"), field="default_branch"),
        commit=commit,
        license=_optional_string(data.get("license"), field="license"),
        year=_optional_integer(data.get("year"), field="year", minimum=1000),
        authors=_strings(data["authors"], field="authors", minimum=1) if "authors" in data else (),
    )
    identity_fields = (source.canonical_url, source.doi, source.zotero_key)
    if source_type is SourceType.PAPER and not any(identity_fields):
        raise DomainError("SOURCE_IDENTITY_MISSING", "paper Source has no canonical identity")
    if source_type is SourceType.WEB and (
        source.canonical_url is None or source.captured_at is None
    ):
        raise DomainError("SOURCE_IDENTITY_MISSING", "web Source lacks URL or capture time")
    if source_type is SourceType.BOOK and not any(
        (source.isbn, source.doi, source.zotero_key, source.canonical_url)
    ):
        raise DomainError("SOURCE_IDENTITY_MISSING", "book Source has no canonical identity")
    if source_type is SourceType.OSS and not all(
        (
            source.canonical_url,
            source.repository_host,
            source.repository_path,
            source.commit,
            source.license,
        )
    ):
        raise DomainError("SOURCE_IDENTITY_MISSING", "OSS Source has incomplete immutable identity")
    return source


def _parse_transition(value: object) -> TypeTransition:
    data = _mapping(value, field="type_history item")
    _exact_keys(data, required={"from", "to", "changed_at", "actor"}, field="type_history item")
    from_type = _enum(NoteType, data["from"], field="type_history.from")
    to_type = _enum(NoteType, data["to"], field="type_history.to")
    if from_type is not NoteType.IDEA or to_type is not NoteType.CONCEPT:
        raise DomainError("NOTE_TRANSITION_INVALID", "only Idea-to-Concept history is valid in v2")
    return TypeTransition(
        from_type=from_type,
        to_type=to_type,
        changed_at=_datetime(data["changed_at"], field="type_history.changed_at"),
        actor=_actor(data["actor"], field="type_history.actor"),
    )


def _parse_note(data: dict[str, Any]) -> Note:
    required = {
        "schema_version",
        "id",
        "kind",
        "note_type",
        "title",
        "visibility",
        "record_status",
        "maturity",
        "created",
        "updated",
        "tags",
        "type_history",
    }
    _exact_keys(data, required=required, field="Note")
    object_id, title, visibility, record_status = _base_object(data, ObjectKind.NOTE)
    note_type = _enum(NoteType, data["note_type"], field="note_type")
    maturity = _enum(Maturity, data["maturity"], field="maturity")
    history = tuple(
        _parse_transition(item) for item in _sequence(data["type_history"], field="type_history")
    )
    if note_type is NoteType.IDEA and maturity not in {Maturity.SEED, Maturity.DEVELOPING}:
        raise DomainError("NOTE_MATURITY_INVALID", "Idea maturity must be seed or developing")
    if note_type is NoteType.CONCEPT and len(history) > 1:
        raise DomainError("NOTE_HISTORY_INVALID", "Concept has more than one v2 type transition")
    if note_type is not NoteType.CONCEPT and history:
        raise DomainError("NOTE_HISTORY_INVALID", "only Concept may contain v2 type history")
    return Note(
        id=object_id,
        note_type=note_type,
        title=title,
        visibility=visibility,
        record_status=record_status,
        maturity=maturity,
        created=_date(data["created"], field="created"),
        updated=_date(data["updated"], field="updated"),
        tags=_tags(data["tags"]),
        type_history=history,
    )


def _parse_snippet(data: dict[str, Any]) -> Snippet:
    required = {
        "schema_version",
        "id",
        "kind",
        "title",
        "source_id",
        "repository_host",
        "repository_path",
        "commit",
        "path",
        "start_line",
        "end_line",
        "license",
        "publication_approved",
        "visibility",
        "record_status",
        "created",
        "updated",
        "tags",
    }
    _exact_keys(data, required=required, field="Snippet")
    object_id, title, visibility, record_status = _base_object(data, ObjectKind.SNIPPET)
    repository_path = _string(data["repository_path"], field="repository_path")
    commit = _string(data["commit"], field="commit")
    path = _string(data["path"], field="path")
    start_line = _integer(data["start_line"], field="start_line", minimum=1)
    end_line = _integer(data["end_line"], field="end_line", minimum=1)
    if REPOSITORY_PATH_RE.fullmatch(repository_path) is None or COMMIT_RE.fullmatch(commit) is None:
        raise DomainError("FIELD_INVALID", "Snippet repository identity is invalid")
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", path):
        raise DomainError("FIELD_INVALID", "Snippet path must be relative")
    if start_line > end_line:
        raise DomainError("SNIPPET_RANGE_INVALID", "Snippet line range is reversed")
    return Snippet(
        id=object_id,
        title=title,
        source_id=ObjectId.parse(data["source_id"], expected_kind=ObjectKind.SOURCE),
        repository_host=_string(data["repository_host"], field="repository_host"),
        repository_path=repository_path,
        commit=commit,
        path=path,
        start_line=start_line,
        end_line=end_line,
        license=_string(data["license"], field="license"),
        publication_approved=_boolean(data["publication_approved"], field="publication_approved"),
        visibility=visibility,
        record_status=record_status,
        created=_date(data["created"], field="created"),
        updated=_date(data["updated"], field="updated"),
        tags=_tags(data["tags"]),
    )


def _parse_input_ref(value: object) -> InputRef:
    data = _mapping(value, field="input_ref")
    _exact_keys(data, required={"object_id"}, optional={"section_id"}, field="input_ref")
    return InputRef(
        object_id=ObjectId.parse(data["object_id"]),
        section_id=SectionId.parse(data["section_id"]) if "section_id" in data else None,
    )


def _parse_ai_artifact(data: dict[str, Any]) -> AIArtifact:
    required = {
        "schema_version",
        "id",
        "kind",
        "artifact_type",
        "title",
        "visibility",
        "record_status",
        "review_status",
        "created",
        "input_refs",
        "generated_by",
        "model",
        "prompt_ref",
        "reviewed_by",
        "reviewed_at",
    }
    _exact_keys(data, required=required, field="AI Artifact")
    object_id, title, visibility, record_status = _base_object(data, ObjectKind.AI_ARTIFACT)
    if visibility is not Visibility.PRIVATE:
        raise DomainError("AI_VISIBILITY_INVALID", "AI Artifact must remain private")
    review_status = _enum(ReviewStatus, data["review_status"], field="review_status")
    reviewed_by = _optional_string(data["reviewed_by"], field="reviewed_by")
    reviewed_at = _optional_datetime(data["reviewed_at"], field="reviewed_at")
    reviewed = reviewed_by is not None and reviewed_at is not None
    if review_status is ReviewStatus.UNREVIEWED and (
        reviewed_by is not None or reviewed_at is not None
    ):
        raise DomainError("AI_REVIEW_INVALID", "unreviewed Artifact has review provenance")
    if review_status is not ReviewStatus.UNREVIEWED and not reviewed:
        raise DomainError("AI_REVIEW_INVALID", "reviewed Artifact lacks review provenance")
    input_refs = tuple(
        _parse_input_ref(item) for item in _sequence(data["input_refs"], field="input_refs")
    )
    if len(input_refs) != len(set(input_refs)):
        raise DomainError("FIELD_INVALID", "input_refs contains duplicates")
    return AIArtifact(
        id=object_id,
        artifact_type=_enum(ArtifactType, data["artifact_type"], field="artifact_type"),
        title=title,
        visibility=visibility,
        record_status=record_status,
        review_status=review_status,
        created=_date(data["created"], field="created"),
        input_refs=input_refs,
        generated_by=_string(data["generated_by"], field="generated_by"),
        model=_string(data["model"], field="model"),
        prompt_ref=_optional_string(data["prompt_ref"], field="prompt_ref"),
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
    )


def _parse_citation(value: object) -> Citation:
    data = _mapping(value, field="citation")
    _exact_keys(data, required={"source_id", "locator"}, field="citation")
    return Citation(
        source_id=ObjectId.parse(data["source_id"], expected_kind=ObjectKind.SOURCE),
        locator=parse_locator(data["locator"]),
    )


def _metadata_blocks(
    content: str, pattern: re.Pattern[str], *, role: SectionRole
) -> tuple[FactBlock | AIBlock, ...]:
    blocks: list[FactBlock | AIBlock] = []
    cursor = 0
    for match in pattern.finditer(content):
        if content[cursor : match.start()].strip():
            raise DomainError("NOTE_BLOCK_METADATA_MISSING", f"{role.value} content lacks metadata")
        try:
            metadata_value = yaml.safe_load(match.group("meta"))
        except yaml.YAMLError as error:
            raise DomainError(
                "NOTE_BLOCK_METADATA_INVALID", "block metadata is invalid YAML"
            ) from error
        metadata = _mapping(metadata_value, field=f"{role.value} metadata")
        block_text = match.group("text").strip()
        if not block_text:
            raise DomainError("NOTE_BLOCK_EMPTY", f"{role.value} block is empty")
        if role is SectionRole.FACT:
            _exact_keys(metadata, required={"citations"}, field="fact metadata")
            citations = tuple(
                _parse_citation(item)
                for item in _sequence(metadata["citations"], field="fact citations")
            )
            if not citations or len(citations) != len(set(citations)):
                raise DomainError("FACT_CITATION_INVALID", "Fact citations are empty or duplicated")
            blocks.append(FactBlock(text=block_text, citations=citations))
        else:
            _exact_keys(metadata, required={"artifact_id"}, field="AI metadata")
            blocks.append(
                AIBlock(
                    text=block_text,
                    artifact_id=ObjectId.parse(
                        metadata["artifact_id"], expected_kind=ObjectKind.AI_ARTIFACT
                    ),
                )
            )
        cursor = match.end()
    if content[cursor:].strip():
        raise DomainError("NOTE_BLOCK_METADATA_MISSING", f"{role.value} content lacks metadata")
    return tuple(blocks)


def parse_note_body(text: str, note_id: ObjectId) -> NoteBody:
    if note_id.kind is not ObjectKind.NOTE:
        raise DomainError("OBJECT_KIND_MISMATCH", "Note body requires a Note ID")
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        raise DomainError("NOTE_SECTION_MISSING", "Note has no role-based sections")
    preamble = text[: matches[0].start()].strip()
    if preamble and not re.fullmatch(r"#[^\r\n]*(?:\r?\n)?", preamble):
        raise DomainError("NOTE_BODY_INVALID", "unexpected content before the first Note section")
    sections: list[NoteSection] = []
    seen: set[SectionId] = set()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        role = _enum(SectionRole, match.group("role"), field="section role")
        section_id = SectionId.parse(match.group("id"))
        if section_id in seen:
            raise DomainError("SECTION_ID_DUPLICATE", f"duplicate section ID: {section_id}")
        seen.add(section_id)
        content = text[match.end() : end].strip()
        if role in {SectionRole.HUMAN, SectionRole.EVOLUTION}:
            blocks: tuple[HumanBlock | FactBlock | AIBlock, ...] = (
                (HumanBlock(text=content),) if content else ()
            )
        elif role is SectionRole.FACT:
            blocks = _metadata_blocks(content, FACT_BLOCK_RE, role=role)
        else:
            blocks = _metadata_blocks(content, AI_BLOCK_RE, role=role)
        sections.append(
            NoteSection(
                section_id=section_id,
                role=role,
                heading=_string(match.group("heading").strip(), field="section heading"),
                blocks=blocks,
            )
        )
    if not any(section.role is SectionRole.HUMAN for section in sections):
        raise DomainError("NOTE_HUMAN_SECTION_MISSING", "Note requires at least one human section")
    return NoteBody(note_id=note_id, sections=tuple(sections))


def parse_object_document(text: str) -> ObjectDocument:
    data, body_text = _parse_frontmatter(text)
    kind = _enum(ObjectKind, data.get("kind"), field="kind")
    durable_object: DurableObject
    if kind is ObjectKind.SOURCE:
        durable_object = _parse_source(data)
    elif kind is ObjectKind.NOTE:
        durable_object = _parse_note(data)
    elif kind is ObjectKind.SNIPPET:
        durable_object = _parse_snippet(data)
    else:
        durable_object = _parse_ai_artifact(data)
    if isinstance(durable_object, Note):
        body: str | NoteBody = parse_note_body(body_text, durable_object.id)
    else:
        body = body_text
    return ObjectDocument(object=durable_object, body=body)


def parse_relation_shard(text: str) -> RelationShard:
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise DomainError("RELATION_PARSE_INVALID", "relation shard is not valid YAML") from error
    data = _mapping(value, field="relation shard")
    _exact_keys(data, required={"schema_version", "from_id", "relations"}, field="relation shard")
    if data["schema_version"] != RELATION_SCHEMA_VERSION:
        raise DomainError("RELATION_VERSION_UNSUPPORTED", "unsupported relation schema version")
    relations: list[Relation] = []
    for item in _sequence(data["relations"], field="relations"):
        relation = _mapping(item, field="relation")
        _exact_keys(
            relation,
            required={"to_id", "relation_type", "created_at", "actor"},
            optional={"to_section_id", "locator", "reason"},
            field="relation",
        )
        relations.append(
            Relation(
                to_id=ObjectId.parse(relation["to_id"]),
                relation_type=_enum(RelationType, relation["relation_type"], field="relation_type"),
                created_at=_datetime(relation["created_at"], field="created_at"),
                actor=_actor(relation["actor"]),
                to_section_id=(
                    SectionId.parse(relation["to_section_id"])
                    if "to_section_id" in relation
                    else None
                ),
                locator=parse_locator(relation["locator"]) if "locator" in relation else None,
                reason=_optional_string(relation.get("reason"), field="reason"),
            )
        )
    return RelationShard(from_id=ObjectId.parse(data["from_id"]), relations=tuple(relations))


def _actor_data(actor: Actor) -> dict[str, Any]:
    return {"type": actor.type.value, "id": actor.id}


def _snapshot_data(snapshot: SnapshotRef) -> dict[str, Any]:
    return {
        "provider": snapshot.provider,
        "identifier": snapshot.identifier,
        "captured_at": snapshot.captured_at.isoformat(),
        "content_hash": snapshot.content_hash,
    }


def locator_data(locator: Locator) -> dict[str, Any]:
    optional: dict[str, Any]
    if isinstance(locator, PaperLocator):
        data: dict[str, Any] = {"locator_version": LOCATOR_VERSION, "source_type": "paper"}
        optional = {
            "page": locator.page,
            "page_label": locator.page_label,
            "section": locator.section,
            "figure": locator.figure,
            "table": locator.table,
        }
    elif isinstance(locator, WebLocator):
        data = {
            "locator_version": LOCATOR_VERSION,
            "source_type": "web",
            "snapshot_ref": _snapshot_data(locator.snapshot_ref),
        }
        optional = {
            "heading_path": list(locator.heading_path) if locator.heading_path else None,
            "paragraph": locator.paragraph,
        }
    elif isinstance(locator, BookLocator):
        data = {"locator_version": LOCATOR_VERSION, "source_type": "book"}
        optional = {
            "edition": locator.edition,
            "isbn": locator.isbn,
            "chapter": locator.chapter,
            "page": locator.page,
            "location": locator.location,
        }
    else:
        data = {
            "locator_version": LOCATOR_VERSION,
            "source_type": "oss",
            "repository_host": locator.repository_host,
            "repository_path": locator.repository_path,
            "commit": locator.commit,
            "path": locator.path,
        }
        optional = {
            "start_line": locator.start_line,
            "end_line": locator.end_line,
            "symbol": locator.symbol,
        }
    data.update({key: value for key, value in optional.items() if value is not None})
    return data


def _object_data(durable_object: DurableObject) -> dict[str, Any]:
    common: dict[str, Any] = {
        "schema_version": OBJECT_CONTRACT_VERSION,
        "id": durable_object.id.value,
        "kind": durable_object.id.kind.value,
    }
    if isinstance(durable_object, Source):
        common.update(
            {
                "source_type": durable_object.source_type.value,
                "title": durable_object.title,
                "visibility": durable_object.visibility.value,
                "record_status": durable_object.record_status.value,
                "workflow_stage": durable_object.workflow_stage.value,
                "created": durable_object.created.isoformat(),
                "updated": durable_object.updated.isoformat(),
            }
        )
        optional: dict[str, Any] = {
            "captured_at": durable_object.captured_at.isoformat()
            if durable_object.captured_at
            else None,
            "canonical_url": durable_object.canonical_url,
            "snapshot_ref": _snapshot_data(durable_object.snapshot_ref)
            if durable_object.snapshot_ref
            else None,
            "zotero_library_id": durable_object.zotero_library_id,
            "zotero_key": durable_object.zotero_key,
            "attachment_key": durable_object.attachment_key,
            "isbn": durable_object.isbn,
            "doi": durable_object.doi,
            "repository_host": durable_object.repository_host,
            "repository_path": durable_object.repository_path,
            "default_branch": durable_object.default_branch,
            "commit": durable_object.commit,
            "license": durable_object.license,
            "year": durable_object.year,
            "authors": list(durable_object.authors) if durable_object.authors else None,
        }
        common.update({key: value for key, value in optional.items() if value is not None})
        common["tags"] = list(durable_object.tags)
        return common
    if isinstance(durable_object, Note):
        common.update(
            {
                "note_type": durable_object.note_type.value,
                "title": durable_object.title,
                "visibility": durable_object.visibility.value,
                "record_status": durable_object.record_status.value,
                "maturity": durable_object.maturity.value,
                "created": durable_object.created.isoformat(),
                "updated": durable_object.updated.isoformat(),
                "tags": list(durable_object.tags),
                "type_history": [
                    {
                        "from": item.from_type.value,
                        "to": item.to_type.value,
                        "changed_at": item.changed_at.isoformat(),
                        "actor": _actor_data(item.actor),
                    }
                    for item in durable_object.type_history
                ],
            }
        )
        return common
    if isinstance(durable_object, Snippet):
        common.update(
            {
                "title": durable_object.title,
                "source_id": durable_object.source_id.value,
                "repository_host": durable_object.repository_host,
                "repository_path": durable_object.repository_path,
                "commit": durable_object.commit,
                "path": durable_object.path,
                "start_line": durable_object.start_line,
                "end_line": durable_object.end_line,
                "license": durable_object.license,
                "publication_approved": durable_object.publication_approved,
                "visibility": durable_object.visibility.value,
                "record_status": durable_object.record_status.value,
                "created": durable_object.created.isoformat(),
                "updated": durable_object.updated.isoformat(),
                "tags": list(durable_object.tags),
            }
        )
        return common
    common.update(
        {
            "artifact_type": durable_object.artifact_type.value,
            "title": durable_object.title,
            "visibility": durable_object.visibility.value,
            "record_status": durable_object.record_status.value,
            "review_status": durable_object.review_status.value,
            "created": durable_object.created.isoformat(),
            "input_refs": [
                {
                    "object_id": item.object_id.value,
                    **({"section_id": item.section_id.value} if item.section_id else {}),
                }
                for item in durable_object.input_refs
            ],
            "generated_by": durable_object.generated_by,
            "model": durable_object.model,
            "prompt_ref": durable_object.prompt_ref,
            "reviewed_by": durable_object.reviewed_by,
            "reviewed_at": durable_object.reviewed_at.isoformat()
            if durable_object.reviewed_at
            else None,
        }
    )
    return common


def _yaml(value: object) -> str:
    return cast(
        str,
        yaml.safe_dump(
            value,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=100,
        ),
    )


def _render_note_body(note: Note, body: NoteBody) -> str:
    if note.id != body.note_id:
        raise DomainError("NOTE_BODY_ID_MISMATCH", "Note body ID does not match frontmatter")
    parts = [f"# {note.title}"]
    for section in body.sections:
        parts.append(
            f"<!-- knowlume:section id={section.section_id.value} role={section.role.value} -->\n"
            f"## {section.heading}"
        )
        rendered_blocks: list[str] = []
        for block in section.blocks:
            if isinstance(block, HumanBlock):
                if section.role not in {SectionRole.HUMAN, SectionRole.EVOLUTION}:
                    raise DomainError(
                        "NOTE_BLOCK_ROLE_MISMATCH", "text block is in a metadata role"
                    )
                rendered_blocks.append(block.text)
            elif isinstance(block, FactBlock):
                if section.role is not SectionRole.FACT:
                    raise DomainError(
                        "NOTE_BLOCK_ROLE_MISMATCH", "Fact block is outside a fact section"
                    )
                fact_metadata = {
                    "citations": [
                        {"source_id": item.source_id.value, "locator": locator_data(item.locator)}
                        for item in block.citations
                    ]
                }
                rendered_blocks.append(
                    f"<!-- knowlume:fact\n{_yaml(fact_metadata).rstrip()}\n-->\n{block.text}"
                )
            else:
                if section.role is not SectionRole.AI:
                    raise DomainError(
                        "NOTE_BLOCK_ROLE_MISMATCH", "AI block is outside an AI section"
                    )
                ai_metadata = {"artifact_id": block.artifact_id.value}
                rendered_blocks.append(
                    f"<!-- knowlume:ai\n{_yaml(ai_metadata).rstrip()}\n-->\n{block.text}"
                )
        if rendered_blocks:
            parts.append("\n\n".join(rendered_blocks))
    return "\n\n".join(parts)


def note_body_data(body: NoteBody) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for section in body.sections:
        blocks: list[dict[str, Any]] = []
        for block in section.blocks:
            if isinstance(block, HumanBlock):
                blocks.append({"kind": "text", "text": block.text})
            elif isinstance(block, FactBlock):
                blocks.append(
                    {
                        "kind": "fact",
                        "text": block.text,
                        "citations": [
                            {
                                "source_id": citation.source_id.value,
                                "locator": locator_data(citation.locator),
                            }
                            for citation in block.citations
                        ],
                    }
                )
            else:
                blocks.append(
                    {
                        "kind": "ai",
                        "text": block.text,
                        "artifact_id": block.artifact_id.value,
                    }
                )
        sections.append(
            {
                "section_id": section.section_id.value,
                "role": section.role.value,
                "heading": section.heading,
                "blocks": blocks,
            }
        )
    return {
        "schema_version": OBJECT_CONTRACT_VERSION,
        "note_id": body.note_id.value,
        "sections": sections,
    }


def render_object_document(document: ObjectDocument) -> str:
    durable_object = document.object
    if isinstance(durable_object, Note):
        if not isinstance(document.body, NoteBody):
            raise DomainError("NOTE_BODY_INVALID", "Note document needs a normalized Note body")
        body = _render_note_body(durable_object, document.body)
    else:
        if not isinstance(document.body, str):
            raise DomainError("OBJECT_BODY_INVALID", "non-Note document body must be text")
        body = document.body.strip()
    return f"---\n{_yaml(_object_data(durable_object)).rstrip()}\n---\n\n{body}\n"


def render_relation_shard(shard: RelationShard) -> str:
    relations: list[dict[str, Any]] = []
    for relation in shard.relations:
        data: dict[str, Any] = {
            "to_id": relation.to_id.value,
            "relation_type": relation.relation_type.value,
        }
        if relation.to_section_id is not None:
            data["to_section_id"] = relation.to_section_id.value
        if relation.locator is not None:
            data["locator"] = locator_data(relation.locator)
        if relation.reason is not None:
            data["reason"] = relation.reason
        data["created_at"] = relation.created_at.isoformat()
        data["actor"] = _actor_data(relation.actor)
        relations.append(data)
    return _yaml(
        {
            "schema_version": RELATION_SCHEMA_VERSION,
            "from_id": shard.from_id.value,
            "relations": relations,
        }
    )
