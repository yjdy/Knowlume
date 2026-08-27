from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from phase0_support import (
    INTERFACE_SCHEMA_DIR,
    ROOT,
    V1_FIXTURES,
    V1_SCHEMA_DIR,
    V1_SECTION_RE,
    V2_FIXTURES,
    V2_SCHEMA_DIR,
    V2_SECTION_RE,
    collect_objects,
    load_json,
    load_markdown,
    load_schemas,
    load_yaml,
    migration_report_semantic_errors,
    parse_v2_note_body,
    relation_cardinality_errors,
    semantic_v2_object_errors,
    semantic_v2_relation_errors,
    validation_errors,
)

ContractBundle = tuple[dict[str, dict[str, Any]], Any]
ObjectMap = dict[str, dict[str, Any]]


@pytest.fixture(scope="module")
def v1_contracts() -> ContractBundle:
    return load_schemas(V1_SCHEMA_DIR)


@pytest.fixture(scope="module")
def v2_contracts() -> ContractBundle:
    return load_schemas(V2_SCHEMA_DIR)


@pytest.fixture(scope="module")
def interface_contracts() -> ContractBundle:
    return load_schemas(INTERFACE_SCHEMA_DIR)


@pytest.fixture(scope="module")
def v2_objects() -> ObjectMap:
    return collect_objects(V2_FIXTURES / "valid")


def test_v1_schemas_and_fixtures_remain_executable(v1_contracts: ContractBundle) -> None:
    schemas, registry = v1_contracts
    assert set(schemas) == {"locator", "objects", "relations"}
    assert all("/v1/" in schema["$id"] for schema in schemas.values())
    for path in sorted((V1_FIXTURES / "valid").glob("*.md")):
        frontmatter, _ = load_markdown(path)
        assert validation_errors(frontmatter, schemas["objects"], registry) == [], path
    relations = load_yaml(V1_FIXTURES / "valid" / "relations.yaml")
    assert validation_errors(relations, schemas["relations"], registry) == []


def test_v1_invalid_schema_fixtures_remain_rejected(v1_contracts: ContractBundle) -> None:
    schemas, registry = v1_contracts
    cases = [
        ("overloaded-status-source.md", "objects"),
        ("web-locator-missing-snapshot.yaml", "locator"),
        ("claim-relation.yaml", "relations"),
    ]
    for filename, schema_name in cases:
        path = V1_FIXTURES / "invalid" / filename
        data = load_markdown(path)[0] if path.suffix == ".md" else load_yaml(path)
        assert validation_errors(data, schemas[schema_name], registry), filename


def test_v1_templates_preserve_fixed_section_syntax() -> None:
    expected = {
        "sec_original_facts",
        "sec_my_interpretation",
        "sec_ai_inference",
        "sec_view_evolution",
    }
    for path in sorted((ROOT / "templates" / "v1" / "notes").glob("*.md")):
        assert set(V1_SECTION_RE.findall(path.read_text(encoding="utf-8"))) == expected


def test_v2_schemas_are_executable(v2_contracts: ContractBundle) -> None:
    schemas, _ = v2_contracts
    assert set(schemas) == {"locator", "note-body", "objects", "relations"}
    assert all("/v2/" in schema["$id"] for schema in schemas.values())


def test_v2_valid_objects_match_frontmatter_schema(
    v2_contracts: ContractBundle, v2_objects: ObjectMap
) -> None:
    schemas, registry = v2_contracts
    assert len(v2_objects) >= 10
    for path in sorted((V2_FIXTURES / "valid").glob("*.md")):
        frontmatter, _ = load_markdown(path)
        assert validation_errors(frontmatter, schemas["objects"], registry) == [], path


def test_v2_valid_note_bodies_and_semantics(
    v2_contracts: ContractBundle, v2_objects: ObjectMap
) -> None:
    schemas, registry = v2_contracts
    for path in sorted((V2_FIXTURES / "valid").glob("*.md")):
        frontmatter, _ = load_markdown(path)
        if frontmatter["kind"] != "note":
            assert semantic_v2_object_errors(path, v2_objects) == [], path
            continue
        body, parse_errors = parse_v2_note_body(path)
        assert parse_errors == [], path
        assert validation_errors(body, schemas["note-body"], registry) == [], path
        assert semantic_v2_object_errors(path, v2_objects, body) == [], path


def test_v2_valid_relation_shards_and_cardinality(
    v2_contracts: ContractBundle, v2_objects: ObjectMap
) -> None:
    schemas, registry = v2_contracts
    sections: dict[str, set[str]] = {}
    for path in sorted((V2_FIXTURES / "valid").glob("*.md")):
        frontmatter, _ = load_markdown(path)
        if frontmatter["kind"] == "note":
            body, _ = parse_v2_note_body(path)
            sections[frontmatter["id"]] = {section["section_id"] for section in body["sections"]}
    documents = []
    for path in sorted((V2_FIXTURES / "valid" / "relations").glob("*.yaml")):
        document = load_yaml(path)
        assert validation_errors(document, schemas["relations"], registry) == [], path
        assert semantic_v2_relation_errors(path, document, v2_objects, sections) == [], path
        documents.append(document)
    assert relation_cardinality_errors(v2_objects, documents) == []
    audit_edges = [
        (document["from_id"], relation["to_id"])
        for document in documents
        for relation in document["relations"]
        if relation["relation_type"] == "promoted_from"
    ]
    assert audit_edges
    assert all(v2_objects[source]["visibility"] == "public" for source, _ in audit_edges)
    assert all(v2_objects[target]["visibility"] == "private" for _, target in audit_edges)


@pytest.mark.parametrize("filename", ["idea-mature.md", "idea-evergreen.md"])
def test_v2_invalid_object_schema_fixtures(
    v2_contracts: ContractBundle, filename: str
) -> None:
    schemas, registry = v2_contracts
    frontmatter, _ = load_markdown(V2_FIXTURES / "invalid" / filename)
    assert validation_errors(frontmatter, schemas["objects"], registry), filename


@pytest.mark.parametrize(
    "filename",
    ["web-locator-missing-snapshot.yaml", "book-page-missing-edition.yaml"],
)
def test_v2_invalid_locator_fixtures(
    v2_contracts: ContractBundle, filename: str
) -> None:
    schemas, registry = v2_contracts
    data = load_yaml(V2_FIXTURES / "invalid" / filename)
    assert validation_errors(data, schemas["locator"], registry), filename


@pytest.mark.parametrize(
    "filename",
    [
        "missing-human-section.md",
        "duplicate-section.md",
        "unknown-role.md",
        "fact-missing-citation.md",
    ],
)
def test_v2_invalid_body_fixtures(
    v2_contracts: ContractBundle, filename: str
) -> None:
    schemas, registry = v2_contracts
    path = V2_FIXTURES / "invalid" / filename
    body, parse_errors = parse_v2_note_body(path)
    schema_errors = validation_errors(body, schemas["note-body"], registry)
    assert parse_errors or schema_errors, filename


@pytest.mark.parametrize(
    "filename",
    ["fact-source-mismatch.md", "ai-unpromoted.md", "snippet-line-range.md"],
)
def test_v2_semantically_invalid_object_fixtures(
    v2_contracts: ContractBundle, v2_objects: ObjectMap, filename: str
) -> None:
    schemas, registry = v2_contracts
    path = V2_FIXTURES / "invalid" / filename
    frontmatter, _ = load_markdown(path)
    assert validation_errors(frontmatter, schemas["objects"], registry) == []
    objects = dict(v2_objects)
    objects[frontmatter["id"]] = frontmatter
    body = None
    if frontmatter["kind"] == "note":
        body, parse_errors = parse_v2_note_body(path)
        assert parse_errors == []
        assert validation_errors(body, schemas["note-body"], registry) == []
    assert semantic_v2_object_errors(path, objects, body), filename


@pytest.mark.parametrize(
    ("filename", "expected_error"),
    [
        ("wrong-kind.yaml", "invalid kind pair for cites"),
        ("duplicate-key.yaml", "duplicate canonical relation key"),
        ("public-private.yaml", "public object has a private content dependency"),
        ("noncanonical-related.yaml", "related_to is not stored in canonical ID order"),
        ("shard-owner-mismatch.yaml", "relation shard filename does not match from_id"),
    ],
)
def test_v2_semantically_invalid_relation_fixtures(
    v2_contracts: ContractBundle,
    v2_objects: ObjectMap,
    filename: str,
    expected_error: str,
) -> None:
    schemas, registry = v2_contracts
    path = V2_FIXTURES / "invalid" / "relations" / filename
    document = load_yaml(path)
    assert validation_errors(document, schemas["relations"], registry) == []
    sections = {
        object_id: {
            section["section_id"]
            for section in parse_v2_note_body(object_path)[0]["sections"]
        }
        for object_id, object_path in _valid_note_paths().items()
    }
    errors = semantic_v2_relation_errors(path, document, v2_objects, sections)
    assert expected_error in errors, (filename, errors)


@pytest.mark.parametrize(
    ("note_type", "expected_error"),
    [
        ("literature", "Literature Note has no summarizes relation"),
        ("synthesis", "mature/public Synthesis has fewer than two targets"),
    ],
)
def test_v2_invalid_relation_cardinality_fixtures(
    v2_objects: ObjectMap, note_type: str, expected_error: str
) -> None:
    relation_documents = [
        load_yaml(path)
        for path in sorted((V2_FIXTURES / "valid" / "relations").glob("*.yaml"))
    ]
    invalid_path = next(
        (V2_FIXTURES / "invalid" / "cardinality" / note_type).glob("*.yaml")
    )
    invalid_document = load_yaml(invalid_path)
    relation_documents = [
        document
        for document in relation_documents
        if document["from_id"] != invalid_document["from_id"]
    ]
    relation_documents.append(invalid_document)
    errors = relation_cardinality_errors(v2_objects, relation_documents)
    assert any(expected_error in error for error in errors), errors


def _valid_note_paths() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted((V2_FIXTURES / "valid").glob("*.md")):
        frontmatter, _ = load_markdown(path)
        if frontmatter["kind"] == "note":
            result[frontmatter["id"]] = path
    return result


def test_v2_templates_use_role_based_sections() -> None:
    note_templates = sorted((ROOT / "templates" / "v2" / "notes").glob("*.md"))
    assert {path.stem for path in note_templates} == {"idea", "literature", "concept", "synthesis"}
    for path in note_templates:
        text = path.read_text(encoding="utf-8")
        roles = [match.group(2) for match in V2_SECTION_RE.finditer(text)]
        assert "human" in roles, path
        assert "<!-- section_id:" not in text, path


def test_projection_contracts_are_executable() -> None:
    v1 = sqlite3.connect(":memory:")
    v1.executescript((V1_SCHEMA_DIR / "sqlite-projection-v1.sql").read_text(encoding="utf-8"))
    assert v1.execute("PRAGMA user_version").fetchone() == (1,)

    v2 = sqlite3.connect(":memory:")
    v2.executescript((V2_SCHEMA_DIR / "sqlite-projection-v2.sql").read_text(encoding="utf-8"))
    assert v2.execute("PRAGMA user_version").fetchone() == (2,)
    tables = {
        row[0]
        for row in v2.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    required_tables = {
        "objects",
        "type_transitions",
        "relations",
        "sections",
        "segments",
        "citations",
        "fts_segments",
    }
    assert required_tables <= tables
    assert [row[1] for row in v2.execute("PRAGMA table_info(objects)")] == [
        "id",
        "kind",
        "subtype",
        "path",
        "title",
        "visibility",
        "record_status",
        "workflow_stage",
        "maturity",
        "review_status",
        "created_at",
        "updated_at",
        "checksum",
    ]
    assert [row[1] for row in v2.execute("PRAGMA table_info(segments)")] == [
        "segment_id",
        "object_id",
        "section_id",
        "provenance_role",
        "text",
        "ordinal",
        "ai_artifact_id",
    ]
    fts_columns = {row[1] for row in v2.execute("PRAGMA table_info(fts_segments)")}
    assert {"segment_id", "object_id", "section_id", "provenance_role"} <= fts_columns
    citation_pk = [
        row[1]
        for row in sorted(
            (row for row in v2.execute("PRAGMA table_info(citations)") if row[5]),
            key=lambda row: row[5],
        )
    ]
    assert citation_pk == ["segment_id", "ordinal"]
    relation_pk = [
        row[1]
        for row in sorted(
            (row for row in v2.execute("PRAGMA table_info(relations)") if row[5]),
            key=lambda row: row[5],
        )
    ]
    assert relation_pk == [
        "from_id",
        "to_id",
        "to_section_id",
        "relation_type",
        "locator",
    ]
    segment_foreign_keys = {
        (row[2], row[3], row[4]) for row in v2.execute("PRAGMA foreign_key_list(segments)")
    }
    assert {
        ("sections", "object_id", "object_id"),
        ("sections", "section_id", "section_id"),
        ("objects", "ai_artifact_id", "id"),
    } <= segment_foreign_keys

    object_rows = [
        (
            "note_test",
            "note",
            "concept",
            "notes/test.md",
            "Test",
            "private",
            "active",
            None,
            "developing",
            None,
            "2026-08-26",
            "2026-08-26",
            "note-hash",
        ),
        (
            "src_one",
            "source",
            "paper",
            "sources/one.md",
            "One",
            "private",
            "active",
            "processed",
            None,
            None,
            "2026-08-26",
            "2026-08-26",
            "one-hash",
        ),
        (
            "src_two",
            "source",
            "paper",
            "sources/two.md",
            "Two",
            "private",
            "active",
            "processed",
            None,
            None,
            "2026-08-26",
            "2026-08-26",
            "two-hash",
        ),
    ]
    v2.executemany(
        "INSERT INTO objects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        object_rows,
    )
    v2.execute(
        "INSERT INTO sections VALUES (?, ?, ?, ?, ?)",
        ("note_test", "sec_fact", "fact", "Facts", 0),
    )
    v2.execute(
        "INSERT INTO segments VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("seg_test", "note_test", "sec_fact", "fact", "A fact", 0, None),
    )
    v2.executemany(
        "INSERT INTO citations VALUES (?, ?, ?, ?)",
        [
            ("seg_test", 0, "src_one", '{"page":1}'),
            ("seg_test", 1, "src_two", '{"page":2}'),
        ],
    )
    assert v2.execute(
        "SELECT source_id FROM citations WHERE segment_id = ? ORDER BY ordinal",
        ("seg_test",),
    ).fetchall() == [("src_one",), ("src_two",)]
    v2.execute(
        "INSERT INTO fts_segments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("Test", "A fact", "", "seg_test", "note_test", "sec_fact", "fact", "private", "active"),
    )
    fts_query = (
        "SELECT segment_id, object_id, section_id, provenance_role "
        "FROM fts_segments WHERE fts_segments MATCH 'fact'"
    )
    assert v2.execute(
        fts_query
    ).fetchone() == ("seg_test", "note_test", "sec_fact", "fact")


def test_interface_and_migration_report_contracts(
    interface_contracts: ContractBundle,
) -> None:
    schemas, registry = interface_contracts
    assert set(schemas) == {
        "add-result-v1",
        "cli-envelope-v1",
        "migration-report-v1",
        "update-check-result-v1",
    }
    assert all("v1.schema.json" in schema["$id"] for schema in schemas.values())
    envelope = load_json(ROOT / "tests" / "fixtures" / "interfaces" / "valid-cli-envelope.json")
    assert validation_errors(envelope, schemas["cli-envelope-v1"], registry) == []
    findings: dict[str, dict[str, Any]] = {}
    for path in sorted((ROOT / "tests" / "fixtures" / "migration").glob("*.json")):
        report = load_json(path)
        assert validation_errors(report, schemas["migration-report-v1"], registry) == [], path
        assert migration_report_semantic_errors(report) == [], path
        assert report["mode"] == "dry-run", path
        findings.update({finding["code"]: finding for finding in report["findings"]})
    assert findings["SECTION_ROLE_MAPPED"]["kind"] == "change"
    assert findings["EVERGREEN_TYPE_AMBIGUOUS"]["kind"] == "decision"
    assert findings["FACT_CITATION_UNRESOLVED"]["kind"] == "blocker"
    assert findings["AI_ARTIFACT_AUDIT_MISSING"]["kind"] == "blocker"
    ambiguous = findings["SOURCE_RELATION_SEMANTICS_AMBIGUOUS"]
    assert ambiguous["details"]["inference_policy"] == "prohibited"


def test_add_result_contract(interface_contracts: ContractBundle) -> None:
    schemas, registry = interface_contracts
    fixture_dir = ROOT / "tests" / "fixtures" / "interfaces"
    for path in sorted(fixture_dir.glob("valid-add-result-*.json")):
        result = load_json(path)
        assert validation_errors(result, schemas["add-result-v1"], registry) == [], path

        envelope = {
            "interface_version": 1,
            "command": "add",
            "success": True,
            "exit_code": 0,
            "data": result,
            "warnings": [],
            "errors": [],
        }
        assert validation_errors(envelope, schemas["cli-envelope-v1"], registry) == [], path

    for path in sorted(fixture_dir.glob("invalid-add-result-*.json")):
        result = load_json(path)
        assert validation_errors(result, schemas["add-result-v1"], registry), path


def test_update_check_result_contract(interface_contracts: ContractBundle) -> None:
    schemas, registry = interface_contracts
    fixture_dir = ROOT / "tests" / "fixtures" / "interfaces"
    result = load_json(fixture_dir / "valid-update-check-result.json")
    assert validation_errors(result, schemas["update-check-result-v1"], registry) == []
    envelope = {
        "interface_version": 1,
        "command": "update-check",
        "success": True,
        "exit_code": 0,
        "data": result,
        "warnings": [],
        "errors": [],
    }
    assert validation_errors(envelope, schemas["cli-envelope-v1"], registry) == []

    invalid = load_json(fixture_dir / "invalid-update-check-result.json")
    assert validation_errors(invalid, schemas["update-check-result-v1"], registry)


def test_v2_contracts_do_not_reintroduce_obsolete_note_fields() -> None:
    forbidden = {"source_ids", "related_notes", "supersedes", "superseded_by", "ai_assisted"}
    schema = json.loads((V2_SCHEMA_DIR / "objects.schema.json").read_text(encoding="utf-8"))
    note_properties = schema["$defs"]["note"]["properties"]
    assert forbidden.isdisjoint(note_properties)
    assert "evergreen" not in note_properties["note_type"]["enum"]


def test_internal_documentation_links_resolve() -> None:
    docs = [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "CLI.md",
        *sorted((ROOT / "plan").rglob("*.md")),
        *sorted((ROOT / "schemas").rglob("README.md")),
        *sorted((ROOT / "templates").rglob("README.md")),
    ]
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    broken: list[str] = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for target in link_re.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            if relative and not (path.parent / relative).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    assert broken == []
