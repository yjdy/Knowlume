from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas/interfaces"
FIXTURES = ROOT / "tests/fixtures/interfaces"


def _load_schemas() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in SCHEMAS.glob("*.schema.json"):
        document = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        Draft202012Validator.check_schema(document)
        schemas[path.name] = document
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    for path in (ROOT / "schemas/v2").glob("*.schema.json"):
        document = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    return schemas, registry


def _errors(document: object, schema: dict[str, Any], registry: Registry) -> list[str]:
    validator = Draft202012Validator(
        schema, registry=registry, format_checker=FormatChecker()
    )
    return [error.message for error in validator.iter_errors(document)]


@pytest.mark.parametrize(
    ("schema_name", "valid_name", "invalid_name"),
    [
        (
            "grep-result-v1.schema.json",
            "valid-grep-result.json",
            "invalid-grep-result-absolute-path.json",
        ),
        (
            "get-result-v1.schema.json",
            "valid-get-result.json",
            "invalid-get-result-absolute-path.json",
        ),
        (
            "index-result-v1.schema.json",
            "valid-index-result.json",
            "invalid-index-result-state.json",
        ),
        (
            "search-result-v1.schema.json",
            "valid-search-result.json",
            "invalid-search-result-missing-identity.json",
        ),
        (
            "context-result-v1.schema.json",
            "valid-context-result.json",
            "invalid-context-result-absolute-path.json",
        ),
    ],
)
def test_phase3_result_contracts_accept_valid_and_reject_invalid(
    schema_name: str, valid_name: str, invalid_name: str
) -> None:
    schemas, registry = _load_schemas()
    valid = json.loads((FIXTURES / valid_name).read_text(encoding="utf-8"))
    invalid = json.loads((FIXTURES / invalid_name).read_text(encoding="utf-8"))
    assert _errors(valid, schemas[schema_name], registry) == []
    assert _errors(invalid, schemas[schema_name], registry)


def test_public_safe_search_requires_a_positive_item_audit() -> None:
    schemas, registry = _load_schemas()
    document = json.loads(
        (FIXTURES / "invalid-search-result-public-audit.json").read_text(encoding="utf-8")
    )
    assert _errors(document, schemas["search-result-v1.schema.json"], registry)


@pytest.mark.parametrize(
    ("fixture", "result_schema"),
    [
        ("golden-grep-envelope.json", "grep-result-v1.schema.json"),
        ("golden-get-envelope.json", "get-result-v1.schema.json"),
        ("golden-index-status-envelope.json", "index-result-v1.schema.json"),
        ("golden-search-envelope.json", "search-result-v1.schema.json"),
        ("golden-context-envelope.json", "context-result-v1.schema.json"),
    ],
)
def test_phase3_golden_envelopes_validate(fixture: str, result_schema: str) -> None:
    schemas, registry = _load_schemas()
    document = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    assert _errors(document, schemas["cli-envelope-v1.schema.json"], registry) == []
    assert _errors(document["data"], schemas[result_schema], registry) == []
