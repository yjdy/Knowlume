from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/phase5"


@cache
def validator(name: str) -> Draft202012Validator:
    registry = Registry()
    documents: dict[str, Any] = {}
    for directory in ("schemas/v2", "schemas/interfaces", "schemas/transactions/v1"):
        for path in (ROOT / directory).glob("*.schema.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(document)
            documents[path.name] = document
            registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    return Draft202012Validator(documents[name], registry=registry, format_checker=FormatChecker())


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_phase5_new_and_legacy_artifact_contracts() -> None:
    check = validator("objects.schema.json")
    for document in fixture("valid-artifacts.json"):
        assert not list(check.iter_errors(document)), document
    for document in fixture("invalid-artifacts.json"):
        assert list(check.iter_errors(document)), document


@pytest.mark.parametrize(
    "path",
    ["a:stream", "a/", "a//b", "a/./b", "./a", ".", "a\n", "a\\b", "/a", "../a"],
)
def test_new_evidence_path_schema_matches_runtime_rejections(path: str) -> None:
    document = fixture("golden-ai-review.json")["data"]
    document["path"] = path
    assert list(validator("ai-review-result-v1.schema.json").iter_errors(document))


@pytest.mark.parametrize("name", [" reviewer", "reviewer ", "reviewer\n", "", "\t", "a\x00b"])
def test_new_evidence_attribution_schema_matches_runtime_rejections(name: str) -> None:
    document = fixture("golden-ai-promote.json")["data"]
    document["promotion"]["actor"]["id"] = name
    assert list(validator("ai-promote-result-v1.schema.json").iter_errors(document))


@pytest.mark.parametrize(
    ("name", "schema"),
    [
        ("ai-list", "ai-list-result-v1"),
        ("ai-review", "ai-review-result-v1"),
        ("ai-promote", "ai-promote-result-v1"),
        ("doctor-v1", "doctor-result-v1"),
        ("doctor-v2", "doctor-result-v2"),
    ],
)
def test_phase5_golden_envelopes_and_required_results(name: str, schema: str) -> None:
    document = fixture(f"golden-{name}.json")
    assert not list(validator("cli-envelope-v1.schema.json").iter_errors(document))
    check = validator(f"{schema}.schema.json")
    assert not list(check.iter_errors(document["data"]))
    for field in document["data"]:
        missing = dict(document["data"])
        del missing[field]
        assert list(check.iter_errors(missing)), field
    extra = dict(document["data"], unknown=True)
    assert list(check.iter_errors(extra))


@pytest.mark.parametrize("path", ["../escape", "C:/private", "/private", "a\\b", "a/../b"])
def test_phase5_machine_results_reject_unsafe_paths(path: str) -> None:
    document = fixture("golden-ai-review.json")["data"]
    document["path"] = path
    assert list(validator("ai-review-result-v1.schema.json").iter_errors(document))


def test_phase5_promotion_contract_preserves_human_attribution() -> None:
    check = validator("ai-promote-result-v1.schema.json")
    document = fixture("golden-ai-promote.json")["data"]
    document["promotion"]["actor"]["type"] = "system"
    assert list(check.iter_errors(document))
    document["promotion"]["actor"] = {"type": "human", "id": " "}
    assert list(check.iter_errors(document))


def test_phase5_unknown_report_evidence_and_probe_versions_fail_closed() -> None:
    for name, schema in [("ai-review", "ai-review-result-v1"), ("doctor-v2", "doctor-result-v2")]:
        document = fixture(f"golden-{name}.json")["data"]
        key = "evidence_version" if name == "ai-review" else "report_version"
        document[key] = 999
        assert list(validator(f"{schema}.schema.json").iter_errors(document))
    doctor = fixture("golden-doctor-v2.json")["data"]
    doctor["probes"] = ["model"]
    assert list(validator("doctor-result-v2.schema.json").iter_errors(doctor))


def test_phase5_transaction_operation_labels_keep_manifest_shape() -> None:
    original = json.loads(
        (ROOT / "tests/fixtures/transactions/v1/valid/manifest.json").read_text(encoding="utf-8")
    )
    check = validator("transaction-manifest.schema.json")
    for operation in ("ai-review", "ai-promote", "relation-update", "migration"):
        candidate = copy.deepcopy(original)
        candidate["operation"] = operation
        assert not list(check.iter_errors(candidate))
    original["operation"] = "model-execute"
    assert list(check.iter_errors(original))
