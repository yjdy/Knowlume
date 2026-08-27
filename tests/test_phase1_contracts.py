from __future__ import annotations

import json
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]


def _schema(path: str) -> dict[str, Any]:
    document = json.loads((ROOT / path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(document)
    return cast(dict[str, Any], document)


def _errors(document: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in sorted(validator.iter_errors(document), key=str)]


def _config_semantic_errors(document: dict[str, Any]) -> list[str]:
    paths = [PurePosixPath(value) for value in document["vault"].values()]
    errors: list[str] = []
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                errors.append(f"configured Vault roots overlap: {left} and {right}")
    return errors


def test_portable_config_schema_template_and_positive_fixture() -> None:
    schema = _schema("schemas/config/v1/knowlume.schema.json")
    template = tomllib.loads(
        (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
    )
    fixture = tomllib.loads(
        (ROOT / "tests/fixtures/config/v1/valid/knowlume.toml").read_text(encoding="utf-8")
    )
    assert template == fixture
    assert _errors(template, schema) == []
    assert _config_semantic_errors(template) == []


def test_invalid_portable_config_fixtures_fail_for_the_intended_reason() -> None:
    schema = _schema("schemas/config/v1/knowlume.schema.json")
    fixture_root = ROOT / "tests/fixtures/config/v1/invalid"
    results: dict[str, list[str]] = {}
    for path in sorted(fixture_root.glob("*.toml")):
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        results[path.name] = _errors(document, schema) + _config_semantic_errors(document)
    assert all(results.values())
    assert any("1 was expected" in error for error in results["unsupported-version.toml"])
    assert any("overlap" in error for error in results["overlapping-roots.toml"])


def test_transaction_manifest_schema_and_fixtures() -> None:
    schema = _schema("schemas/transactions/v1/transaction-manifest.schema.json")
    valid = json.loads(
        (ROOT / "tests/fixtures/transactions/v1/valid/manifest.json").read_text(encoding="utf-8")
    )
    invalid = json.loads(
        (ROOT / "tests/fixtures/transactions/v1/invalid/unsafe-path.json").read_text(
            encoding="utf-8"
        )
    )
    assert _errors(valid, schema) == []
    assert _errors(invalid, schema)


def test_finding_v1_schema_and_fixtures() -> None:
    schema = _schema("schemas/interfaces/finding-v1.schema.json")
    valid = json.loads(
        (ROOT / "tests/fixtures/interfaces/valid-finding.json").read_text(encoding="utf-8")
    )
    invalid = json.loads(
        (ROOT / "tests/fixtures/interfaces/invalid-finding-absolute-path.json").read_text(
            encoding="utf-8"
        )
    )
    assert _errors(valid, schema) == []
    assert _errors(invalid, schema)


def test_phase1_contract_versions_are_independent() -> None:
    config = _schema("schemas/config/v1/knowlume.schema.json")
    transaction = _schema("schemas/transactions/v1/transaction-manifest.schema.json")
    finding = _schema("schemas/interfaces/finding-v1.schema.json")
    assert config["properties"]["config_version"]["const"] == 1
    assert config["properties"]["object_contract_version"]["const"] == 2
    assert transaction["properties"]["transaction_version"]["const"] == 1
    assert finding["properties"]["finding_version"]["const"] == 1
