from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from knowlume.adapters.contract_v2 import (
    locator_data,
    parse_locator,
    parse_object_document,
    parse_relation_shard,
    render_object_document,
    render_relation_shard,
)
from knowlume.domain.models import Actor, Note, NoteBody, ObjectDocument, Relation, RelationShard
from knowlume.domain.validation import (
    validate_object_references,
    validate_relation_cardinality,
    validate_relation_shard,
)
from knowlume.domain.values import ActorType, DomainError, ObjectId, RelationType, SectionRole

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "v2"


def _document(path: Path) -> ObjectDocument:
    return parse_object_document(path.read_text(encoding="utf-8"))


def _valid_catalog() -> dict[ObjectId, ObjectDocument]:
    documents = [_document(path) for path in sorted((FIXTURES / "valid").glob("*.md"))]
    return {document.object.id: document for document in documents}


def _sections(objects: dict[ObjectId, ObjectDocument]) -> dict[ObjectId, set[str]]:
    return {
        object_id: {str(section.section_id) for section in document.body.sections}
        for object_id, document in objects.items()
        if isinstance(document.body, NoteBody)
    }


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "valid").glob("*.md")), ids=lambda path: path.name
)
def test_valid_v2_object_round_trip(path: Path) -> None:
    original = _document(path)
    rendered = render_object_document(original)
    assert parse_object_document(rendered) == original


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "valid" / "relations").glob("*.yaml")), ids=lambda path: path.name
)
def test_valid_relation_round_trip(path: Path) -> None:
    original = parse_relation_shard(path.read_text(encoding="utf-8"))
    assert parse_relation_shard(render_relation_shard(original)) == original


@pytest.mark.parametrize(
    "value",
    [
        {
            "locator_version": 2,
            "source_type": "paper",
            "page": 3,
            "section": "Methods",
        },
        {
            "locator_version": 2,
            "source_type": "web",
            "snapshot_ref": {
                "provider": "archive",
                "identifier": "snapshot-1",
                "captured_at": "2026-08-27T00:00:00+00:00",
                "content_hash": "sha256:" + "0" * 64,
            },
            "heading_path": ["Architecture"],
        },
        {
            "locator_version": 2,
            "source_type": "book",
            "isbn": "9781449373320",
            "page": 42,
        },
        {
            "locator_version": 2,
            "source_type": "oss",
            "repository_host": "github.com",
            "repository_path": "example/project",
            "commit": "0" * 40,
            "path": "src/core.py",
            "start_line": 10,
            "end_line": 12,
        },
    ],
    ids=("paper", "web", "book", "oss"),
)
def test_every_locator_form_round_trips(value: dict[str, object]) -> None:
    parsed = parse_locator(value)
    assert parse_locator(locator_data(parsed)) == parsed


@pytest.mark.parametrize("relation_type", list(RelationType))
def test_every_relation_form_round_trips(relation_type: RelationType) -> None:
    source = ObjectId("note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0")
    target_prefix = {
        RelationType.CITES: "src",
        RelationType.DERIVED_FROM: "src",
        RelationType.SUMMARIZES: "src",
        RelationType.SYNTHESIZES: "src",
        RelationType.SUPPORTS: "note",
        RelationType.CONTRADICTS: "note",
        RelationType.RELATED_TO: "note",
        RelationType.SNIPPET_FROM: "src",
        RelationType.PROMOTED_FROM: "ai",
        RelationType.SUPERSEDES: "note",
    }[relation_type]
    target = ObjectId(f"{target_prefix}_01JSTAG7N9Q3V5X8Y2Z4A6B8D9")
    shard = RelationShard(
        source,
        (
            Relation(
                target,
                relation_type,
                datetime(2026, 8, 27, tzinfo=UTC),
                Actor(ActorType.HUMAN, "reviewer"),
                reason="round trip",
            ),
        ),
    )
    assert parse_relation_shard(render_relation_shard(shard)) == shard


def test_newer_object_contract_fails_closed() -> None:
    text = (FIXTURES / "valid/idea-note.md").read_text(encoding="utf-8")
    with pytest.raises(DomainError) as caught:
        parse_object_document(text.replace("schema_version: 2", "schema_version: 99", 1))
    assert caught.value.code == "OBJECT_VERSION_UNSUPPORTED"


def test_source_free_notes_remain_human_provenance() -> None:
    for name in ("idea-note.md", "public-idea-note.md"):
        document = _document(FIXTURES / "valid" / name)
        assert isinstance(document.object, Note)
        assert isinstance(document.body, NoteBody)
        assert all(section.role is SectionRole.HUMAN for section in document.body.sections)


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("duplicate-section.md", "SECTION_ID_DUPLICATE"),
        ("fact-missing-citation.md", "NOTE_BLOCK_METADATA_MISSING"),
        ("idea-evergreen.md", "NOTE_MATURITY_INVALID"),
        ("idea-mature.md", "NOTE_MATURITY_INVALID"),
        ("missing-human-section.md", "NOTE_HUMAN_SECTION_MISSING"),
        ("snippet-line-range.md", "SNIPPET_RANGE_INVALID"),
        ("unknown-role.md", "FIELD_INVALID"),
    ],
)
def test_structurally_invalid_v2_objects_have_stable_codes(name: str, code: str) -> None:
    with pytest.raises(DomainError) as caught:
        _document(FIXTURES / "invalid" / name)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("book-page-missing-edition.yaml", "LOCATOR_INVALID"),
        ("web-locator-missing-snapshot.yaml", "FIELD_MISSING"),
    ],
)
def test_invalid_locators_have_stable_codes(name: str, code: str) -> None:
    value = yaml.safe_load((FIXTURES / "invalid" / name).read_text(encoding="utf-8"))
    with pytest.raises(DomainError) as caught:
        parse_locator(value)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("ai-unpromoted.md", "AI_ARTIFACT_UNPROMOTED"),
        ("fact-source-mismatch.md", "FACT_LOCATOR_MISMATCH"),
    ],
)
def test_cross_object_invalid_documents_have_stable_codes(name: str, code: str) -> None:
    objects = _valid_catalog()
    document = _document(FIXTURES / "invalid" / name)
    objects[document.object.id] = document
    assert code in {error.code for error in validate_object_references(document, objects)}


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("duplicate-key.yaml", "RELATION_DUPLICATE"),
        ("noncanonical-related.yaml", "RELATION_NOT_CANONICAL"),
        ("shard-owner-mismatch.yaml", "RELATION_SHARD_OWNER_MISMATCH"),
        ("wrong-kind.yaml", "RELATION_KIND_INVALID"),
    ],
)
def test_invalid_relation_shards_have_stable_codes(name: str, code: str) -> None:
    objects = _valid_catalog()
    path = FIXTURES / "invalid" / "relations" / name
    shard = parse_relation_shard(path.read_text(encoding="utf-8"))
    errors = validate_relation_shard(
        shard, shard_name=path.stem, objects=objects, sections=_sections(objects)
    )
    assert code in {error.code for error in errors}


def test_relation_cardinality_is_domain_validated() -> None:
    objects = _valid_catalog()
    shards: dict[ObjectId, RelationShard] = {}
    for path in sorted((FIXTURES / "invalid" / "cardinality").rglob("*.yaml")):
        shard = parse_relation_shard(path.read_text(encoding="utf-8"))
        shards[shard.from_id] = shard
    codes = {error.code for error in validate_relation_cardinality(objects, shards)}
    assert {"LITERATURE_SUMMARY_MISSING", "SYNTHESIS_TARGETS_INSUFFICIENT"} <= codes
