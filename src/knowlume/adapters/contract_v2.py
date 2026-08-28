from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
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
    enum_value,
)

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
SECTION_RE = re.compile(
    r"<!--\s*knowlume:section\s+id=(sec_[a-z0-9][a-z0-9_-]{2,63})\s+role=([a-z]+)\s*-->"
    r"\s*\r?\n##\s+([^\r\n]+)(?:\r?\n|\Z)",
)
FACT_RE = re.compile(
    r"<!--\s*knowlume:fact\r?\n(.*?)\r?\n-->\s*(.+?)(?=(?:\r?\n){2,}<!--\s*knowlume:fact|\Z)",
    re.DOTALL,
)
AI_RE = re.compile(
    r"<!--\s*knowlume:ai\r?\n(.*?)\r?\n-->\s*(.+?)(?=(?:\r?\n){2,}<!--\s*knowlume:ai|\Z)",
    re.DOTALL,
)
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def _mapping(value: object, field: str = "document") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainError("FIELD_INVALID", f"{field} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DomainError("FIELD_INVALID", f"{field} must be an array")
    return list(value)


def _exact_keys(data: Mapping[str, Any], *, required: set[str], allowed: set[str]) -> None:
    missing = sorted(required - data.keys())
    if missing:
        raise DomainError("FIELD_MISSING", f"missing field: {missing[0]}")
    unknown = sorted(data.keys() - allowed)
    if unknown:
        raise DomainError("FIELD_UNKNOWN", f"unknown field: {unknown[0]}")


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DomainError("FIELD_INVALID", f"{field} must be a non-empty string")
    return value


def _optional_string(value: object, field: str) -> str | None:
    return None if value is None else _string(value, field)


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DomainError("FIELD_INVALID", f"{field} must be an integer")
    return value


def _date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        raise DomainError("FIELD_INVALID", f"{field} must be a date")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_string(value, field))
    except ValueError as error:
        raise DomainError("FIELD_INVALID", f"{field} must be an ISO date") from error


def _datetime(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(_string(value, field).replace("Z", "+00:00"))
        except ValueError as error:
            raise DomainError("FIELD_INVALID", f"{field} must be an ISO date-time") from error
    if result.tzinfo is None:
        raise DomainError("FIELD_INVALID", f"{field} must include a timezone")
    return result


def _tags(value: object) -> tuple[str, ...]:
    tags = tuple(_string(item, "tag") for item in _sequence(value, "tags"))
    if len(tags) != len(set(tags)) or any(not TAG_RE.fullmatch(tag) for tag in tags):
        raise DomainError("FIELD_INVALID", "tags must be unique canonical values")
    return tags


def _actor(value: object) -> Actor:
    data = _mapping(value, "actor")
    _exact_keys(data, required={"type", "id"}, allowed={"type", "id"})
    return Actor(
        enum_value(ActorType, data["type"], field="actor type"), _string(data["id"], "actor.id")
    )


def _snapshot(value: object) -> SnapshotRef:
    data = _mapping(value, "snapshot_ref")
    keys = {"provider", "identifier", "captured_at", "content_hash"}
    _exact_keys(data, required=keys, allowed=keys)
    return SnapshotRef(
        _string(data["provider"], "provider"),
        _string(data["identifier"], "identifier"),
        _datetime(data["captured_at"], "captured_at"),
        _string(data["content_hash"], "content_hash"),
    )


def parse_locator(value: object) -> Locator:
    data = _mapping(value, "locator")
    if data.get("locator_version") != LOCATOR_VERSION:
        raise DomainError("LOCATOR_VERSION_UNSUPPORTED", "unsupported locator version")
    source_type = enum_value(SourceType, data.get("source_type"), field="locator source type")
    base = {"locator_version", "source_type"}
    if source_type is SourceType.PAPER:
        allowed = base | {"page", "page_label", "section", "figure", "table"}
        _exact_keys(data, required=base, allowed=allowed)
        return PaperLocator(
            _integer(data["page"], "page") if "page" in data else None,
            _optional_string(data.get("page_label"), "page_label"),
            _optional_string(data.get("section"), "section"),
            _optional_string(data.get("figure"), "figure"),
            _optional_string(data.get("table"), "table"),
        )
    if source_type is SourceType.WEB:
        allowed = base | {"snapshot_ref", "heading_path", "paragraph"}
        _exact_keys(data, required=base | {"snapshot_ref"}, allowed=allowed)
        headings = tuple(
            _string(item, "heading_path")
            for item in _sequence(data.get("heading_path", []), "heading_path")
        )
        return WebLocator(
            _snapshot(data["snapshot_ref"]),
            headings,
            _integer(data["paragraph"], "paragraph") if "paragraph" in data else None,
        )
    if source_type is SourceType.BOOK:
        allowed = base | {"edition", "isbn", "chapter", "page", "location"}
        _exact_keys(data, required=base, allowed=allowed)
        return BookLocator(
            _optional_string(data.get("edition"), "edition"),
            _optional_string(data.get("isbn"), "isbn"),
            _optional_string(data.get("chapter"), "chapter"),
            _integer(data["page"], "page") if "page" in data else None,
            _optional_string(data.get("location"), "location"),
        )
    allowed = base | {
        "repository_host",
        "repository_path",
        "commit",
        "path",
        "start_line",
        "end_line",
        "symbol",
    }
    required = base | {"repository_host", "repository_path", "commit", "path"}
    _exact_keys(data, required=required, allowed=allowed)
    return OssLocator(
        repository_host=_string(data["repository_host"], "repository_host"),
        repository_path=_string(data["repository_path"], "repository_path"),
        commit=_string(data["commit"], "commit"),
        path=_string(data["path"], "path"),
        start_line=_integer(data["start_line"], "start_line") if "start_line" in data else None,
        end_line=_integer(data["end_line"], "end_line") if "end_line" in data else None,
        symbol=_optional_string(data.get("symbol"), "symbol"),
    )


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise DomainError("FRONTMATTER_MISSING", "document has no YAML frontmatter")
    try:
        data = _mapping(yaml.safe_load(match.group(1)), "frontmatter")
    except yaml.YAMLError as error:
        raise DomainError("FRONTMATTER_INVALID", "frontmatter is invalid YAML") from error
    return data, text[match.end() :]


def _common(data: dict[str, Any], kind: ObjectKind) -> ObjectId:
    if data.get("schema_version") != OBJECT_CONTRACT_VERSION:
        raise DomainError("OBJECT_VERSION_UNSUPPORTED", "unsupported object Contract version")
    if data.get("kind") != kind.value:
        raise DomainError("OBJECT_KIND_MISMATCH", f"expected object kind {kind.value}")
    object_id = ObjectId(_string(data.get("id"), "id"))
    if object_id.kind is not kind:
        raise DomainError("OBJECT_KIND_MISMATCH", "object ID prefix does not match kind")
    return object_id


COMMON = {"schema_version", "id", "kind", "title", "visibility", "record_status", "created"}


def _parse_source(data: dict[str, Any]) -> Source:
    allowed = COMMON | {
        "source_type",
        "workflow_stage",
        "updated",
        "captured_at",
        "canonical_url",
        "snapshot_ref",
        "zotero_library_id",
        "zotero_library_type",
        "zotero_key",
        "zotero_item_version",
        "synced_at",
        "managed_fields_hash",
        "attachment_key",
        "attachment_version",
        "attachment_filename",
        "attachment_media_type",
        "attachment_size",
        "attachment_sha256",
        "isbn",
        "doi",
        "arxiv_id",
        "arxiv_version",
        "repository_host",
        "repository_path",
        "default_branch",
        "commit",
        "license",
        "year",
        "authors",
        "tags",
    }
    required = COMMON | {"source_type", "workflow_stage", "updated", "tags"}
    _exact_keys(data, required=required, allowed=allowed)
    return Source(
        id=_common(data, ObjectKind.SOURCE),
        source_type=enum_value(SourceType, data["source_type"], field="source type"),
        title=_string(data["title"], "title"),
        visibility=enum_value(Visibility, data["visibility"], field="visibility"),
        record_status=enum_value(RecordStatus, data["record_status"], field="record status"),
        workflow_stage=enum_value(WorkflowStage, data["workflow_stage"], field="workflow stage"),
        created=_date(data["created"], "created"),
        updated=_date(data["updated"], "updated"),
        tags=_tags(data["tags"]),
        captured_at=_datetime(data["captured_at"], "captured_at")
        if data.get("captured_at") is not None
        else None,
        canonical_url=_optional_string(data.get("canonical_url"), "canonical_url"),
        snapshot_ref=_snapshot(data["snapshot_ref"]) if data.get("snapshot_ref") else None,
        zotero_library_id=_optional_string(data.get("zotero_library_id"), "zotero_library_id"),
        zotero_library_type=_optional_string(
            data.get("zotero_library_type"), "zotero_library_type"
        ),
        zotero_key=_optional_string(data.get("zotero_key"), "zotero_key"),
        zotero_item_version=_integer(data["zotero_item_version"], "zotero_item_version")
        if data.get("zotero_item_version") is not None
        else None,
        synced_at=_datetime(data["synced_at"], "synced_at")
        if data.get("synced_at") is not None
        else None,
        managed_fields_hash=_optional_string(
            data.get("managed_fields_hash"), "managed_fields_hash"
        ),
        attachment_key=_optional_string(data.get("attachment_key"), "attachment_key"),
        attachment_version=_integer(data["attachment_version"], "attachment_version")
        if data.get("attachment_version") is not None
        else None,
        attachment_filename=_optional_string(
            data.get("attachment_filename"), "attachment_filename"
        ),
        attachment_media_type=_optional_string(
            data.get("attachment_media_type"), "attachment_media_type"
        ),
        attachment_size=_integer(data["attachment_size"], "attachment_size")
        if data.get("attachment_size") is not None
        else None,
        attachment_sha256=_optional_string(data.get("attachment_sha256"), "attachment_sha256"),
        isbn=_optional_string(data.get("isbn"), "isbn"),
        doi=_optional_string(data.get("doi"), "doi"),
        arxiv_id=_optional_string(data.get("arxiv_id"), "arxiv_id"),
        arxiv_version=_integer(data["arxiv_version"], "arxiv_version")
        if data.get("arxiv_version") is not None
        else None,
        repository_host=_optional_string(data.get("repository_host"), "repository_host"),
        repository_path=_optional_string(data.get("repository_path"), "repository_path"),
        default_branch=_optional_string(data.get("default_branch"), "default_branch"),
        commit=_optional_string(data.get("commit"), "commit"),
        license=_optional_string(data.get("license"), "license"),
        year=_integer(data["year"], "year") if data.get("year") is not None else None,
        authors=tuple(
            _string(item, "author") for item in _sequence(data.get("authors", []), "authors")
        ),
    )


def _transition(value: object) -> TypeTransition:
    data = _mapping(value, "type_history entry")
    keys = {"from", "to", "changed_at", "actor"}
    _exact_keys(data, required=keys, allowed=keys)
    return TypeTransition(
        enum_value(NoteType, data["from"], field="transition source"),
        enum_value(NoteType, data["to"], field="transition target"),
        _datetime(data["changed_at"], "changed_at"),
        _actor(data["actor"]),
    )


def _parse_note(data: dict[str, Any]) -> Note:
    allowed = COMMON | {"note_type", "maturity", "updated", "tags", "type_history"}
    _exact_keys(data, required=allowed, allowed=allowed)
    return Note(
        _common(data, ObjectKind.NOTE),
        enum_value(NoteType, data["note_type"], field="Note type"),
        _string(data["title"], "title"),
        enum_value(Visibility, data["visibility"], field="visibility"),
        enum_value(RecordStatus, data["record_status"], field="record status"),
        enum_value(Maturity, data["maturity"], field="maturity"),
        _date(data["created"], "created"),
        _date(data["updated"], "updated"),
        _tags(data["tags"]),
        tuple(_transition(item) for item in _sequence(data["type_history"], "type_history")),
    )


def _parse_snippet(data: dict[str, Any]) -> Snippet:
    allowed = COMMON | {
        "source_id",
        "repository_host",
        "repository_path",
        "commit",
        "path",
        "start_line",
        "end_line",
        "license",
        "publication_approved",
        "updated",
        "tags",
    }
    _exact_keys(data, required=allowed, allowed=allowed)
    approved = data["publication_approved"]
    if not isinstance(approved, bool):
        raise DomainError("FIELD_INVALID", "publication_approved must be boolean")
    return Snippet(
        id=_common(data, ObjectKind.SNIPPET),
        title=_string(data["title"], "title"),
        source_id=ObjectId(_string(data["source_id"], "source_id")),
        repository_host=_string(data["repository_host"], "repository_host"),
        repository_path=_string(data["repository_path"], "repository_path"),
        commit=_string(data["commit"], "commit"),
        path=_string(data["path"], "path"),
        start_line=_integer(data["start_line"], "start_line"),
        end_line=_integer(data["end_line"], "end_line"),
        license=_string(data["license"], "license"),
        publication_approved=approved,
        visibility=enum_value(Visibility, data["visibility"], field="visibility"),
        record_status=enum_value(RecordStatus, data["record_status"], field="record status"),
        created=_date(data["created"], "created"),
        updated=_date(data["updated"], "updated"),
        tags=_tags(data["tags"]),
    )


def _input_ref(value: object) -> InputRef:
    data = _mapping(value, "input reference")
    _exact_keys(data, required={"object_id"}, allowed={"object_id", "section_id"})
    return InputRef(
        ObjectId(_string(data["object_id"], "object_id")),
        SectionId(_string(data["section_id"], "section_id")) if data.get("section_id") else None,
    )


def _parse_ai(data: dict[str, Any]) -> AIArtifact:
    allowed = COMMON | {
        "artifact_type",
        "review_status",
        "input_refs",
        "generated_by",
        "model",
        "prompt_ref",
        "reviewed_by",
        "reviewed_at",
    }
    _exact_keys(data, required=allowed, allowed=allowed)
    return AIArtifact(
        _common(data, ObjectKind.AI_ARTIFACT),
        enum_value(ArtifactType, data["artifact_type"], field="artifact type"),
        _string(data["title"], "title"),
        enum_value(Visibility, data["visibility"], field="visibility"),
        enum_value(RecordStatus, data["record_status"], field="record status"),
        enum_value(ReviewStatus, data["review_status"], field="review status"),
        _date(data["created"], "created"),
        tuple(_input_ref(item) for item in _sequence(data["input_refs"], "input_refs")),
        _string(data["generated_by"], "generated_by"),
        _string(data["model"], "model"),
        _optional_string(data["prompt_ref"], "prompt_ref"),
        _optional_string(data["reviewed_by"], "reviewed_by"),
        _datetime(data["reviewed_at"], "reviewed_at") if data["reviewed_at"] is not None else None,
    )


def _remove_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    result, cursor = [], 0
    for start, end in ranges:
        result.append(text[cursor:start])
        cursor = end
    result.append(text[cursor:])
    return "".join(result)


def _citation(value: object) -> Citation:
    data = _mapping(value, "citation")
    _exact_keys(data, required={"source_id", "locator"}, allowed={"source_id", "locator"})
    return Citation(
        ObjectId(_string(data["source_id"], "source_id")), parse_locator(data["locator"])
    )


def parse_note_body(text: str, note_id: ObjectId) -> NoteBody:
    matches = list(SECTION_RE.finditer(text))
    sections: list[NoteSection] = []
    for index, match in enumerate(matches):
        content = text[
            match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)
        ].strip()
        role = enum_value(SectionRole, match.group(2), field="section role")
        blocks: list[HumanBlock | FactBlock | AIBlock] = []
        if role in {SectionRole.HUMAN, SectionRole.EVOLUTION}:
            if content:
                blocks.append(HumanBlock(content))
        else:
            pattern = FACT_RE if role is SectionRole.FACT else AI_RE
            ranges: list[tuple[int, int]] = []
            for block_match in pattern.finditer(content):
                metadata = _mapping(yaml.safe_load(block_match.group(1)), "block metadata")
                if role is SectionRole.FACT:
                    citations = tuple(
                        _citation(item)
                        for item in _sequence(metadata.get("citations", []), "citations")
                    )
                    blocks.append(FactBlock(block_match.group(2).strip(), citations))
                else:
                    blocks.append(
                        AIBlock(
                            block_match.group(2).strip(),
                            ObjectId(_string(metadata.get("artifact_id"), "artifact_id")),
                        )
                    )
                ranges.append(block_match.span())
            if _remove_ranges(content, ranges).strip():
                kind = "fact" if role is SectionRole.FACT else "AI"
                raise DomainError("NOTE_BLOCK_METADATA_MISSING", f"{kind} content lacks metadata")
        sections.append(
            NoteSection(SectionId(match.group(1)), role, match.group(3).strip(), tuple(blocks))
        )
    return NoteBody(note_id, tuple(sections))


def parse_object_document(text: str) -> ObjectDocument:
    data, body = _frontmatter(text)
    kind = enum_value(ObjectKind, data.get("kind"), field="object kind")
    parsers = {
        ObjectKind.SOURCE: _parse_source,
        ObjectKind.NOTE: _parse_note,
        ObjectKind.SNIPPET: _parse_snippet,
        ObjectKind.AI_ARTIFACT: _parse_ai,
    }
    durable_object = cast(DurableObject, parsers[kind](data))
    parsed_body: str | NoteBody = (
        parse_note_body(body, durable_object.id)
        if isinstance(durable_object, Note)
        else body.strip()
    )
    return ObjectDocument(durable_object, parsed_body)


def parse_relation_shard(text: str) -> RelationShard:
    try:
        data = _mapping(yaml.safe_load(text), "relation shard")
    except yaml.YAMLError as error:
        raise DomainError("RELATION_PARSE_FAILED", "relation shard is invalid YAML") from error
    _exact_keys(
        data,
        required={"schema_version", "from_id", "relations"},
        allowed={"schema_version", "from_id", "relations"},
    )
    if data["schema_version"] != RELATION_SCHEMA_VERSION:
        raise DomainError("RELATION_VERSION_UNSUPPORTED", "unsupported relation schema version")
    relations: list[Relation] = []
    allowed = {
        "to_id",
        "to_section_id",
        "relation_type",
        "locator",
        "reason",
        "created_at",
        "actor",
    }
    for value in _sequence(data["relations"], "relations"):
        item = _mapping(value, "relation")
        _exact_keys(
            item, required={"to_id", "relation_type", "created_at", "actor"}, allowed=allowed
        )
        relations.append(
            Relation(
                ObjectId(_string(item["to_id"], "to_id")),
                enum_value(RelationType, item["relation_type"], field="relation type"),
                _datetime(item["created_at"], "created_at"),
                _actor(item["actor"]),
                SectionId(_string(item["to_section_id"], "to_section_id"))
                if item.get("to_section_id")
                else None,
                parse_locator(item["locator"]) if item.get("locator") else None,
                _optional_string(item.get("reason"), "reason"),
            )
        )
    return RelationShard(ObjectId(_string(data["from_id"], "from_id")), tuple(relations))


def _actor_data(actor: Actor) -> dict[str, str]:
    return {"type": actor.type.value, "id": actor.id}


def _snapshot_data(value: SnapshotRef) -> dict[str, Any]:
    return {
        "provider": value.provider,
        "identifier": value.identifier,
        "captured_at": value.captured_at.isoformat(),
        "content_hash": value.content_hash,
    }


def locator_data(locator: Locator) -> dict[str, Any]:
    data: dict[str, Any] = {"locator_version": LOCATOR_VERSION}
    if isinstance(locator, PaperLocator):
        data["source_type"] = "paper"
        for key in ("page", "page_label", "section", "figure", "table"):
            if (value := getattr(locator, key)) is not None:
                data[key] = value
    elif isinstance(locator, WebLocator):
        data.update(source_type="web", snapshot_ref=_snapshot_data(locator.snapshot_ref))
        if locator.heading_path:
            data["heading_path"] = list(locator.heading_path)
        if locator.paragraph is not None:
            data["paragraph"] = locator.paragraph
    elif isinstance(locator, BookLocator):
        data["source_type"] = "book"
        for key in ("edition", "isbn", "chapter", "page", "location"):
            if (value := getattr(locator, key)) is not None:
                data[key] = value
    else:
        data.update(
            source_type="oss",
            repository_host=locator.repository_host,
            repository_path=locator.repository_path,
            commit=locator.commit,
            path=locator.path,
        )
        for key in ("start_line", "end_line", "symbol"):
            if (value := getattr(locator, key)) is not None:
                data[key] = value
    return data


def _value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, ObjectId | SectionId):
        return str(value)
    if isinstance(value, Actor):
        return _actor_data(value)
    if isinstance(value, SnapshotRef):
        return _snapshot_data(value)
    if isinstance(value, TypeTransition):
        return {
            "from": value.from_type.value,
            "to": value.to_type.value,
            "changed_at": value.changed_at.isoformat(),
            "actor": _actor_data(value.actor),
        }
    if isinstance(value, InputRef):
        result = {"object_id": str(value.object_id)}
        if value.section_id:
            result["section_id"] = str(value.section_id)
        return result
    if isinstance(value, tuple):
        return [_value(item) for item in value]
    return value


def _object_data(obj: DurableObject) -> dict[str, Any]:
    kind = {Source: "source", Note: "note", Snippet: "snippet", AIArtifact: "ai_artifact"}[
        type(obj)
    ]
    data: dict[str, Any] = {
        "schema_version": OBJECT_CONTRACT_VERSION,
        "id": str(obj.id),
        "kind": kind,
    }
    fields = {
        Source: (
            "source_type",
            "title",
            "visibility",
            "record_status",
            "workflow_stage",
            "created",
            "updated",
            "captured_at",
            "canonical_url",
            "snapshot_ref",
            "zotero_library_id",
            "zotero_library_type",
            "zotero_key",
            "zotero_item_version",
            "synced_at",
            "managed_fields_hash",
            "attachment_key",
            "attachment_version",
            "attachment_filename",
            "attachment_media_type",
            "attachment_size",
            "attachment_sha256",
            "isbn",
            "doi",
            "arxiv_id",
            "arxiv_version",
            "repository_host",
            "repository_path",
            "default_branch",
            "commit",
            "license",
            "year",
            "authors",
            "tags",
        ),
        Note: (
            "note_type",
            "title",
            "visibility",
            "record_status",
            "maturity",
            "created",
            "updated",
            "tags",
            "type_history",
        ),
        Snippet: (
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
        ),
        AIArtifact: (
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
        ),
    }[type(obj)]
    required_values = {
        "tags",
        "type_history",
        "input_refs",
        "prompt_ref",
        "reviewed_by",
        "reviewed_at",
    }
    for field in fields:
        value = getattr(obj, field)
        if value is not None and value != () or field in required_values:
            data[field] = _value(value)
    return data


def object_data(obj: DurableObject) -> dict[str, Any]:
    """Return the normalized JSON-compatible frontmatter representation."""

    return _object_data(obj)


def _yaml(value: object) -> str:
    return cast(
        str,
        yaml.safe_dump(
            value, allow_unicode=True, default_flow_style=False, sort_keys=False, width=4096
        ),
    )


def _render_note_body(note: Note, body: NoteBody) -> str:
    if note.id != body.note_id:
        raise DomainError("NOTE_BODY_ID_MISMATCH", "Note body ID does not match frontmatter")
    parts = [f"# {note.title}"]
    for section in body.sections:
        rendered = [
            f"<!-- knowlume:section id={section.section_id} role={section.role.value} -->",
            f"## {section.heading}",
        ]
        for block in section.blocks:
            if isinstance(block, HumanBlock):
                rendered.append(block.text.rstrip())
            elif isinstance(block, FactBlock):
                meta = {
                    "citations": [
                        {"source_id": str(c.source_id), "locator": locator_data(c.locator)}
                        for c in block.citations
                    ]
                }
                rendered.append(
                    f"<!-- knowlume:fact\n{_yaml(meta).rstrip()}\n-->\n{block.text.rstrip()}"
                )
            else:
                metadata = _yaml({"artifact_id": str(block.artifact_id)}).rstrip()
                rendered.append(f"<!-- knowlume:ai\n{metadata}\n-->\n{block.text.rstrip()}")
        parts.append("\n\n".join(rendered))
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
                            {"source_id": str(c.source_id), "locator": locator_data(c.locator)}
                            for c in block.citations
                        ],
                    }
                )
            else:
                blocks.append(
                    {"kind": "ai", "text": block.text, "artifact_id": str(block.artifact_id)}
                )
        sections.append(
            {
                "section_id": str(section.section_id),
                "role": section.role.value,
                "heading": section.heading,
                "blocks": blocks,
            }
        )
    return {
        "schema_version": OBJECT_CONTRACT_VERSION,
        "note_id": str(body.note_id),
        "sections": sections,
    }


def render_object_document(document: ObjectDocument) -> str:
    if isinstance(document.object, Note):
        if not isinstance(document.body, NoteBody):
            raise DomainError("OBJECT_BODY_INVALID", "Note document needs a normalized Note body")
        body = _render_note_body(document.object, document.body)
    else:
        if not isinstance(document.body, str):
            raise DomainError("OBJECT_BODY_INVALID", "non-Note document body must be text")
        body = document.body.rstrip()
    return f"---\n{_yaml(_object_data(document.object))}---\n\n{body}\n"


def render_relation_shard(shard: RelationShard) -> str:
    relations: list[dict[str, Any]] = []
    for relation in shard.relations:
        item: dict[str, Any] = {
            "to_id": str(relation.to_id),
            "relation_type": relation.relation_type.value,
        }
        if relation.to_section_id:
            item["to_section_id"] = str(relation.to_section_id)
        if relation.locator:
            item["locator"] = locator_data(relation.locator)
        if relation.reason:
            item["reason"] = relation.reason
        item.update(created_at=relation.created_at.isoformat(), actor=_actor_data(relation.actor))
        relations.append(item)
    return _yaml(
        {
            "schema_version": RELATION_SCHEMA_VERSION,
            "from_id": str(shard.from_id),
            "relations": relations,
        }
    )
