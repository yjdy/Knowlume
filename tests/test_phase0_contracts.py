from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from phase0_support import (
    INVALID_FIXTURES,
    ROOT,
    VALID_FIXTURES,
    collect_valid_objects,
    load_markdown,
    load_schemas,
    load_yaml,
    semantic_object_errors,
    semantic_relation_errors,
    validation_errors,
)


@pytest.fixture(scope="module")
def contracts():
    return load_schemas()


def test_phase0_contract_schemas_are_executable(contracts) -> None:
    schemas, _ = contracts
    assert set(schemas) == {"locator", "objects", "relations"}

    connection = sqlite3.connect(":memory:")
    connection.executescript(
        (ROOT / "schemas" / "sqlite-projection-v1.sql").read_text(encoding="utf-8")
    )

    table_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "objects",
        "relations",
        "segments",
        "tags",
        "object_tags",
        "fts_segments",
        "parse_errors",
        "scan_state",
        "index_metadata",
        "schema_metadata",
    } <= table_names

    relation_primary_key = [
        row[1]
        for row in sorted(
            (row for row in connection.execute("PRAGMA table_info(relations)") if row[5]),
            key=lambda row: row[5],
        )
    ]
    assert relation_primary_key == [
        "from_id",
        "to_id",
        "to_section_id",
        "relation_type",
        "locator",
    ]

    unique_object_indexes = [
        row[1]
        for row in connection.execute("PRAGMA index_list(objects)")
        if row[2]
    ]
    assert any(
        [row[2] for row in connection.execute(f"PRAGMA index_info('{index_name}')")]
        == ["path"]
        for index_name in unique_object_indexes
    )
    assert connection.execute("PRAGMA user_version").fetchone() == (1,)


def test_all_valid_object_fixtures_match_schema(contracts) -> None:
    schemas, registry = contracts
    for path in sorted(VALID_FIXTURES.glob("*.md")):
        frontmatter, _ = load_markdown(path)
        assert validation_errors(frontmatter, schemas["objects"], registry) == [], path


def test_valid_objects_are_referentially_safe() -> None:
    objects, _ = collect_valid_objects()
    assert semantic_object_errors(objects) == []


def test_valid_relations_target_objects_or_stable_sections(contracts) -> None:
    schemas, registry = contracts
    relation_document = load_yaml(VALID_FIXTURES / "relations.yaml")
    assert validation_errors(relation_document, schemas["relations"], registry) == []
    objects, sections = collect_valid_objects()
    assert semantic_relation_errors(relation_document, objects, sections) == []


@pytest.mark.parametrize(
    ("filename", "schema_name"),
    [
        ("overloaded-status-source.md", "objects"),
        ("web-locator-missing-snapshot.yaml", "locator"),
        ("claim-relation.yaml", "relations"),
    ],
)
def test_schema_invalid_fixtures_are_rejected(contracts, filename: str, schema_name: str) -> None:
    schemas, registry = contracts
    path = INVALID_FIXTURES / filename
    data = load_markdown(path)[0] if path.suffix == ".md" else load_yaml(path)
    assert validation_errors(data, schemas[schema_name], registry), filename


@pytest.mark.parametrize(
    "filename",
    ["missing-section-relation.yaml", "public-private-relation.yaml"],
)
def test_semantically_invalid_relations_are_rejected(contracts, filename: str) -> None:
    schemas, registry = contracts
    relation_document = load_yaml(INVALID_FIXTURES / filename)
    assert validation_errors(relation_document, schemas["relations"], registry) == []
    objects, sections = collect_valid_objects()
    assert semantic_relation_errors(relation_document, objects, sections), filename


def test_note_templates_freeze_stable_section_syntax() -> None:
    expected = {
        "sec_original_facts",
        "sec_my_interpretation",
        "sec_ai_inference",
        "sec_view_evolution",
    }
    marker = re.compile(r"<!--\s*section_id:\s*(sec_[a-z0-9][a-z0-9_-]{2,63})\s*-->")
    for path in sorted((ROOT / "templates" / "notes").glob("*.md")):
        assert set(marker.findall(path.read_text(encoding="utf-8"))) == expected, path


def test_phase0_template_inventory_is_complete() -> None:
    expected = {
        Path("source-card.md"),
        Path("snippet.md"),
        Path("ai-artifact.md"),
        Path("relations.yaml"),
        Path("notes/literature.md"),
        Path("notes/concept.md"),
        Path("notes/synthesis.md"),
        Path("notes/evergreen.md"),
    }
    actual = {
        path.relative_to(ROOT / "templates")
        for path in (ROOT / "templates").rglob("*")
        if path.is_file()
    }
    assert actual == expected


def test_obsolete_status_field_is_absent_from_valid_contracts() -> None:
    paths = [
        *sorted((ROOT / "schemas").glob("*.schema.json")),
        *sorted((ROOT / "templates").rglob("*.md")),
        *sorted(VALID_FIXTURES.glob("*.md")),
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert re.search(r"(?m)^status\s*:", text) is None, path
