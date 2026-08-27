from __future__ import annotations

import json
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from phase0_support import ROOT

CONFIG_SCHEMA = ROOT / "schemas" / "config" / "v1" / "knowlume.schema.json"
STATE_SCHEMA_DIR = ROOT / "schemas" / "state" / "v1"
CONFIG_FIXTURES = ROOT / "tests" / "fixtures" / "config" / "v1"
STATE_FIXTURES = ROOT / "tests" / "fixtures" / "state" / "v1"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _load_toml(path: Path) -> dict[str, Any]:
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validator(path: Path) -> Draft202012Validator:
    schema = _load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_errors(validator: Draft202012Validator, value: dict[str, Any]) -> list[str]:
    return [error.message for error in sorted(validator.iter_errors(value), key=str)]


def _config_semantic_errors(value: dict[str, Any]) -> list[str]:
    raw_paths = value.get("paths")
    if not isinstance(raw_paths, dict) or not all(
        isinstance(path, str) for path in raw_paths.values()
    ):
        return []
    paths = [PurePosixPath(path).parts for path in raw_paths.values()]
    errors: list[str] = []
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            common = min(len(left), len(right))
            if left[:common] == right[:common]:
                errors.append("configured durable paths must be distinct and non-overlapping")
    return errors


def _transaction_semantic_errors(value: dict[str, Any]) -> list[str]:
    state = value.get("state")
    outcome = value.get("outcome")
    entries = value.get("entries")
    transaction_id = value.get("transaction_id")
    if not isinstance(entries, list):
        return []

    errors: list[str] = []
    allowed_outcomes: dict[str, set[str]] = {
        "locked": {"pending"},
        "staging": {"pending"},
        "staged": {"pending"},
        "committing": {"pending"},
        "committed": {"commit"},
        "rolling_back": {"rollback"},
        "rolled_back": {"rollback"},
        "cleaning": {"commit", "rollback"},
        "complete": {"commit", "rollback"},
    }
    if not isinstance(state, str) or outcome not in allowed_outcomes.get(state, set()):
        errors.append("transaction state and outcome disagree")

    targets = [entry.get("target_path") for entry in entries if isinstance(entry, dict)]
    if len(targets) != len(set(targets)):
        errors.append("transaction target paths must be unique")

    expected_prefix = f".knowlume/transactions/{transaction_id}/"
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for field in ("staged_path", "backup_path"):
            path = entry.get(field)
            if isinstance(path, str) and not path.startswith(expected_prefix):
                errors.append(f"{field} does not belong to transaction_id")

    entry_states = {entry.get("state") for entry in entries if isinstance(entry, dict)}
    if state == "staged" and entry_states != {"staged"}:
        errors.append("staged transaction must have only staged entries")
    if state == "committed" and entry_states != {"applied"}:
        errors.append("committed transaction must have only applied entries")
    if state == "rolled_back" and entry_states != {"restored"}:
        errors.append("rolled-back transaction must have only restored entries")
    if state in {"cleaning", "complete"}:
        terminal_entry_state = "applied" if outcome == "commit" else "restored"
        if entry_states != {terminal_entry_state}:
            errors.append("cleanup entries do not match the recorded outcome")
    return errors


def test_portable_config_v1_schema_and_template_are_executable() -> None:
    validator = _validator(CONFIG_SCHEMA)
    template = _load_toml(ROOT / "templates" / "config" / "v1" / "knowlume.toml")
    assert _schema_errors(validator, template) == []
    assert _config_semantic_errors(template) == []

    for path in sorted((CONFIG_FIXTURES / "valid").glob("*.toml")):
        value = _load_toml(path)
        assert _schema_errors(validator, value) == [], path
        assert _config_semantic_errors(value) == [], path


@pytest.mark.parametrize(
    "filename",
    ["absolute-path.toml", "traversal.toml", "unsupported-version.toml"],
)
def test_invalid_portable_config_schema_fixtures_are_rejected(filename: str) -> None:
    validator = _validator(CONFIG_SCHEMA)
    value = _load_toml(CONFIG_FIXTURES / "invalid" / filename)
    assert _schema_errors(validator, value), filename


def test_overlapping_portable_paths_are_rejected_semantically() -> None:
    validator = _validator(CONFIG_SCHEMA)
    value = _load_toml(CONFIG_FIXTURES / "invalid" / "overlapping-paths.toml")
    assert _schema_errors(validator, value) == []
    assert _config_semantic_errors(value) == [
        "configured durable paths must be distinct and non-overlapping"
    ]


def test_state_v1_schemas_and_valid_fixtures_are_executable() -> None:
    schemas = {path.stem.removesuffix(".schema"): path for path in STATE_SCHEMA_DIR.glob("*.json")}
    assert set(schemas) == {"transaction-manifest", "vault-write-lock"}

    lock_validator = _validator(schemas["vault-write-lock"])
    lock = _load_json(STATE_FIXTURES / "valid" / "vault-write-lock.json")
    assert _schema_errors(lock_validator, lock) == []

    transaction_validator = _validator(schemas["transaction-manifest"])
    for path in sorted((STATE_FIXTURES / "valid").glob("transaction-*.json")):
        value = _load_json(path)
        assert _schema_errors(transaction_validator, value) == [], path
        assert _transaction_semantic_errors(value) == [], path


def test_invalid_transaction_target_is_rejected_by_schema() -> None:
    validator = _validator(STATE_SCHEMA_DIR / "transaction-manifest.schema.json")
    value = _load_json(STATE_FIXTURES / "invalid" / "transaction-unsafe-target.json")
    assert _schema_errors(validator, value)


def test_transaction_state_and_outcome_are_consistent() -> None:
    validator = _validator(STATE_SCHEMA_DIR / "transaction-manifest.schema.json")
    value = _load_json(STATE_FIXTURES / "invalid" / "transaction-outcome-mismatch.json")
    assert _schema_errors(validator, value) == []
    assert _transaction_semantic_errors(value) == ["transaction state and outcome disagree"]


def test_phase1_diagnostic_codes_and_global_vault_syntax_are_frozen() -> None:
    interfaces = (ROOT / "plan" / "interfaces.md").read_text(encoding="utf-8")
    required_codes = {
        "VAULT_REQUIRED",
        "VAULT_NOT_FOUND",
        "VAULT_CONFIG_INVALID",
        "VAULT_CONFIG_UNSUPPORTED",
        "VAULT_AMBIGUOUS",
        "VAULT_SELECTION_CONFLICT",
        "VAULT_TARGET_NOT_EMPTY",
        "VAULT_PATH_UNSAFE",
        "VAULT_UNAVAILABLE",
        "WRITE_CONFLICT",
        "VAULT_LOCKED",
        "TRANSACTION_RECOVERY_REQUIRED",
        "TRANSACTION_MANIFEST_INVALID",
        "TRANSACTION_RECOVERY_CONFLICT",
    }
    assert all(f"`{code}`" in interfaces for code in required_codes)
    assert "`kb --vault PATH scan`" in interfaces
    assert "`kb init PATH` uses its positional path" in interfaces
