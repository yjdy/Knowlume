from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
VALID_FIXTURES = ROOT / "tests" / "fixtures" / "valid"
INVALID_FIXTURES = ROOT / "tests" / "fixtures" / "invalid"

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
SECTION_ID_RE = re.compile(r"<!--\s*section_id:\s*(sec_[a-z0-9][a-z0-9_-]{2,63})\s*-->")


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} must contain a YAML mapping")
    return data


def load_markdown(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise AssertionError(f"{path} has no YAML frontmatter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} frontmatter must be a mapping")
    return data, text[match.end() :]


def load_schemas() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schemas[path.stem.removesuffix(".schema")] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def validation_errors(
    data: dict[str, Any], schema: dict[str, Any], registry: Registry
) -> list[str]:
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )
    return [error.message for error in sorted(validator.iter_errors(data), key=str)]


def collect_valid_objects() -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    objects: dict[str, dict[str, Any]] = {}
    sections: dict[str, set[str]] = {}
    for path in sorted(VALID_FIXTURES.glob("*.md")):
        data, body = load_markdown(path)
        object_id = data["id"]
        if object_id in objects:
            raise AssertionError(f"duplicate object id: {object_id}")
        objects[object_id] = data
        section_ids = SECTION_ID_RE.findall(body)
        if len(section_ids) != len(set(section_ids)):
            raise AssertionError(f"duplicate section_id in {path}")
        sections[object_id] = set(section_ids)
    return objects, sections


def semantic_relation_errors(
    relation_document: dict[str, Any],
    objects: dict[str, dict[str, Any]],
    sections: dict[str, set[str]],
) -> list[str]:
    errors: list[str] = []
    for index, relation in enumerate(relation_document["relations"]):
        prefix = f"relation[{index}]"
        from_id = relation["from_id"]
        to_id = relation["to_id"]
        if from_id not in objects:
            errors.append(f"{prefix}: unknown from_id {from_id}")
            continue
        if to_id not in objects:
            errors.append(f"{prefix}: unknown to_id {to_id}")
            continue

        to_section_id = relation.get("to_section_id")
        if to_section_id and to_section_id not in sections.get(to_id, set()):
            errors.append(f"{prefix}: unknown stable section {to_section_id}")

        source = objects[from_id]
        target = objects[to_id]
        if source["visibility"] == "public" and target["visibility"] == "private":
            errors.append(f"{prefix}: public object depends on private object")

        locator = relation.get("locator")
        if locator and source["kind"] == "source":
            if locator["source_type"] != source["source_type"]:
                errors.append(f"{prefix}: locator source_type does not match source")
    return errors


def semantic_object_errors(objects: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for object_id, data in objects.items():
        if data["kind"] == "note":
            for source_id in data["source_ids"]:
                source = objects.get(source_id)
                if source is None:
                    errors.append(f"{object_id}: unknown source_id {source_id}")
                elif data["visibility"] == "public" and source["visibility"] == "private":
                    errors.append(f"{object_id}: public note depends on private source")
        elif data["kind"] in {"snippet", "ai_artifact"}:
            source_ids = (
                [data["source_id"]] if data["kind"] == "snippet" else data["source_ids"]
            )
            for source_id in source_ids:
                if source_id not in objects:
                    errors.append(f"{object_id}: unknown source_id {source_id}")

        if data["kind"] == "snippet" and data["end_line"] < data["start_line"]:
            errors.append(f"{object_id}: end_line precedes start_line")
    return errors
