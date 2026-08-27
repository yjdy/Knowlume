from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from phase0_support import V2_FIXTURES, V2_SCHEMA_DIR, load_schemas, validation_errors

from knowlume.adapters.contract_v2 import (
    locator_data,
    note_body_data,
    parse_locator,
    parse_object_document,
    parse_relation_shard,
    render_object_document,
    render_relation_shard,
)
from knowlume.domain import (
    AIArtifact,
    DomainError,
    FactBlock,
    Note,
    NoteBody,
    ObjectId,
    ObjectKind,
    SectionRole,
    Snippet,
    Source,
)

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)


def _frontmatter(text: str) -> dict[str, Any]:
    match = FRONTMATTER_RE.match(text)
    assert match is not None
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_typed_object_and_section_ids() -> None:
    source_id = ObjectId.parse("src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0")
    assert source_id.kind is ObjectKind.SOURCE
    with pytest.raises(DomainError, match="invalid object ID") as error:
        ObjectId.parse("source-by-title")
    assert error.value.code == "OBJECT_ID_INVALID"
    with pytest.raises(DomainError) as mismatch:
        ObjectId.parse(source_id.value, expected_kind=ObjectKind.NOTE)
    assert mismatch.value.code == "OBJECT_KIND_MISMATCH"


def test_every_valid_v2_object_round_trips_through_domain_model() -> None:
    schemas, registry = load_schemas(V2_SCHEMA_DIR)
    seen_types: set[type[object]] = set()
    for path in sorted((V2_FIXTURES / "valid").glob("*.md")):
        document = parse_object_document(path.read_text(encoding="utf-8"))
        seen_types.add(type(document.object))
        rendered = render_object_document(document)
        reparsed = parse_object_document(rendered)
        assert reparsed == document, path
        assert validation_errors(_frontmatter(rendered), schemas["objects"], registry) == [], path
        if isinstance(reparsed.object, Note):
            assert isinstance(reparsed.body, NoteBody)
            assert (
                validation_errors(note_body_data(reparsed.body), schemas["note-body"], registry)
                == []
            ), path
            assert any(section.role is SectionRole.HUMAN for section in reparsed.body.sections)
    assert seen_types == {Source, Note, Snippet, AIArtifact}


def test_fact_and_ai_metadata_round_trip_as_typed_blocks() -> None:
    literature = parse_object_document(
        (V2_FIXTURES / "valid" / "literature-note.md").read_text(encoding="utf-8")
    )
    assert isinstance(literature.body, NoteBody)
    fact = literature.body.sections[0].blocks[0]
    assert isinstance(fact, FactBlock)
    assert fact.citations[0].source_id.kind is ObjectKind.SOURCE

    promoted = parse_object_document(
        (V2_FIXTURES / "valid" / "promoted-concept-note.md").read_text(encoding="utf-8")
    )
    assert isinstance(promoted.body, NoteBody)
    assert promoted.body.sections[1].blocks[0].artifact_id.kind is ObjectKind.AI_ARTIFACT  # type: ignore[union-attr]


def test_every_valid_relation_shard_round_trips_and_matches_schema() -> None:
    schemas, registry = load_schemas(V2_SCHEMA_DIR)
    for path in sorted((V2_FIXTURES / "valid" / "relations").glob("*.yaml")):
        shard = parse_relation_shard(path.read_text(encoding="utf-8"))
        rendered = render_relation_shard(shard)
        assert parse_relation_shard(rendered) == shard, path
        data = yaml.safe_load(rendered)
        assert validation_errors(data, schemas["relations"], registry) == [], path


@pytest.mark.parametrize(
    "path",
    sorted((V2_FIXTURES / "valid").glob("*.md")),
    ids=lambda path: Path(path).name,
)
def test_object_parser_never_reads_from_the_filesystem(
    monkeypatch: pytest.MonkeyPatch, path: Path
) -> None:
    text = path.read_text(encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: pytest.fail("unexpected read"))
    parse_object_document(text)


@pytest.mark.parametrize(
    ("filename", "code"),
    [
        ("missing-human-section.md", "NOTE_HUMAN_SECTION_MISSING"),
        ("duplicate-section.md", "SECTION_ID_DUPLICATE"),
        ("unknown-role.md", "FIELD_INVALID"),
        ("fact-missing-citation.md", "NOTE_BLOCK_METADATA_MISSING"),
        ("snippet-line-range.md", "SNIPPET_RANGE_INVALID"),
    ],
)
def test_parser_rejects_invalid_v2_documents_with_typed_errors(filename: str, code: str) -> None:
    text = (V2_FIXTURES / "invalid" / filename).read_text(encoding="utf-8")
    with pytest.raises(DomainError) as error:
        parse_object_document(text)
    assert error.value.code == code


def test_all_locator_variants_round_trip_through_typed_values() -> None:
    values = [
        {"locator_version": 2, "source_type": "paper", "page": 4, "section": "3.2"},
        {
            "locator_version": 2,
            "source_type": "web",
            "snapshot_ref": {
                "provider": "archive",
                "identifier": "snapshot-1",
                "captured_at": "2026-08-27T08:00:00Z",
                "content_hash": f"sha256:{'a' * 64}",
            },
            "heading_path": ["Design", "Storage"],
        },
        {"locator_version": 2, "source_type": "book", "isbn": "9781449373320", "page": 42},
        {
            "locator_version": 2,
            "source_type": "oss",
            "repository_host": "github.com",
            "repository_path": "owner/project",
            "commit": "a" * 40,
            "path": "src/core.py",
            "start_line": 1,
            "end_line": 2,
        },
    ]
    schemas, registry = load_schemas(V2_SCHEMA_DIR)
    for value in values:
        parsed = parse_locator(value)
        normalized = locator_data(parsed)
        assert parse_locator(normalized) == parsed
        assert validation_errors(normalized, schemas["locator"], registry) == []
