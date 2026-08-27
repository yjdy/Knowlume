from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas"
V1_SCHEMA_DIR = SCHEMA_ROOT / "v1"
V2_SCHEMA_DIR = SCHEMA_ROOT / "v2"
INTERFACE_SCHEMA_DIR = SCHEMA_ROOT / "interfaces"
V1_FIXTURES = ROOT / "tests" / "fixtures" / "v1"
V2_FIXTURES = ROOT / "tests" / "fixtures" / "v2"

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
V1_SECTION_RE = re.compile(r"<!--\s*section_id:\s*(sec_[a-z0-9][a-z0-9_-]{2,63})\s*-->")
V2_SECTION_RE = re.compile(
    r"<!--\s*knowlume:section\s+id=(sec_[a-z0-9][a-z0-9_-]{2,63})\s+role=([a-z]+)\s*-->"
)
FACT_RE = re.compile(
    r"<!--\s*knowlume:fact\r?\n(.*?)\r?\n-->\s*(.+?)(?=(?:\r?\n){2,}<!--\s*knowlume:fact|\Z)",
    re.DOTALL,
)
AI_RE = re.compile(
    r"<!--\s*knowlume:ai\r?\n(.*?)\r?\n-->\s*(.+?)(?=(?:\r?\n){2,}<!--\s*knowlume:ai|\Z)",
    re.DOTALL,
)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} must contain a YAML mapping")
    return data


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} must contain a JSON object")
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


def load_schemas(*directories: Path) -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for directory in directories:
        for path in sorted(directory.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            key = path.stem.removesuffix(".schema")
            schemas[key] = schema
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


def collect_objects(directory: Path) -> dict[str, dict[str, Any]]:
    objects: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.md")):
        data, _ = load_markdown(path)
        object_id = data["id"]
        if object_id in objects:
            raise AssertionError(f"duplicate object id: {object_id}")
        objects[object_id] = data
    return objects


def _remove_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    pieces: list[str] = []
    cursor = 0
    for start, end in ranges:
        pieces.append(text[cursor:start])
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def parse_v2_note_body(path: Path) -> tuple[dict[str, Any], list[str]]:
    frontmatter, body = load_markdown(path)
    result: dict[str, Any] = {
        "schema_version": 2,
        "note_id": frontmatter["id"],
        "sections": [],
    }
    errors: list[str] = []
    matches = list(V2_SECTION_RE.finditer(body))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section_text = body[start:end].strip()
        heading_match = re.match(r"##\s+(.+?)(?:\r?\n|\Z)", section_text)
        if heading_match is None:
            errors.append(f"section {match.group(1)} has no adjacent level-2 heading")
            continue
        role = match.group(2)
        content = section_text[heading_match.end() :].strip()
        section: dict[str, Any] = {
            "section_id": match.group(1),
            "role": role,
            "heading": heading_match.group(1).strip(),
            "blocks": [],
        }
        if role in {"human", "evolution"}:
            if content:
                section["blocks"].append({"kind": "text", "text": content})
        elif role == "fact":
            matched_ranges: list[tuple[int, int]] = []
            for fact_match in FACT_RE.finditer(content):
                metadata = yaml.safe_load(fact_match.group(1))
                if not isinstance(metadata, dict):
                    errors.append(f"section {match.group(1)} has invalid fact metadata")
                    continue
                section["blocks"].append(
                    {
                        "kind": "fact",
                        "text": fact_match.group(2).strip(),
                        "citations": metadata.get("citations", []),
                    }
                )
                matched_ranges.append(fact_match.span())
            if _remove_ranges(content, matched_ranges).strip():
                errors.append(f"section {match.group(1)} has uncited fact content")
        elif role == "ai":
            matched_ranges = []
            for ai_match in AI_RE.finditer(content):
                metadata = yaml.safe_load(ai_match.group(1))
                if not isinstance(metadata, dict):
                    errors.append(f"section {match.group(1)} has invalid AI metadata")
                    continue
                section["blocks"].append(
                    {
                        "kind": "ai",
                        "text": ai_match.group(2).strip(),
                        "artifact_id": metadata.get("artifact_id"),
                    }
                )
                matched_ranges.append(ai_match.span())
            if _remove_ranges(content, matched_ranges).strip():
                errors.append(f"section {match.group(1)} has unbound AI content")
        result["sections"].append(section)
    if frontmatter.get("kind") == "note" and not matches:
        errors.append("Note has no Contract v2 section markers")
    section_ids = [section["section_id"] for section in result["sections"]]
    if len(section_ids) != len(set(section_ids)):
        errors.append("duplicate section_id")
    return result, errors


def semantic_v2_object_errors(
    path: Path,
    objects: dict[str, dict[str, Any]],
    body: dict[str, Any] | None = None,
) -> list[str]:
    data, _ = load_markdown(path)
    errors: list[str] = []
    if data["kind"] == "snippet":
        source = objects.get(data["source_id"])
        if source is None or source.get("source_type") != "oss":
            errors.append("Snippet source must be an existing OSS Source")
        if data["end_line"] < data["start_line"]:
            errors.append("end_line precedes start_line")
    if data["kind"] == "note" and body is not None:
        for section in body["sections"]:
            for block in section["blocks"]:
                if block["kind"] == "fact":
                    for citation in block["citations"]:
                        source = objects.get(citation["source_id"])
                        if source is None:
                            errors.append(f"unknown Source {citation['source_id']}")
                            continue
                        if citation["locator"]["source_type"] != source["source_type"]:
                            errors.append("fact locator source_type does not match Source")
                        if data["visibility"] == "public" and source["visibility"] != "public":
                            errors.append("public Fact depends on private Source")
                if block["kind"] == "ai":
                    artifact = objects.get(block["artifact_id"])
                    if artifact is None or artifact.get("kind") != "ai_artifact":
                        errors.append("AI block references an unknown Artifact")
                    elif artifact["review_status"] != "promoted":
                        errors.append("AI block references an unpromoted Artifact")
    return errors


RELATION_MATRIX: dict[str, tuple[set[str], set[str]]] = {
    "cites": ({"note"}, {"source"}),
    "summarizes": ({"note"}, {"source"}),
    "synthesizes": ({"note"}, {"source", "note"}),
    "supports": ({"source", "note"}, {"note"}),
    "contradicts": ({"source", "note"}, {"note"}),
    "related_to": ({"note"}, {"note"}),
    "snippet_from": ({"snippet"}, {"source"}),
    "derived_from": ({"note", "ai_artifact"}, {"source", "note"}),
    "promoted_from": ({"note"}, {"ai_artifact"}),
    "supersedes": (
        {"source", "note", "snippet", "ai_artifact"},
        {"source", "note", "snippet", "ai_artifact"},
    ),
}
CONTENT_DEPENDENCIES = {
    "cites",
    "summarizes",
    "synthesizes",
    "supports",
    "contradicts",
    "snippet_from",
    "derived_from",
}


def semantic_v2_relation_errors(
    path: Path,
    document: dict[str, Any],
    objects: dict[str, dict[str, Any]],
    sections: dict[str, set[str]],
) -> list[str]:
    errors: list[str] = []
    from_id = document["from_id"]
    if path.stem != from_id:
        errors.append("relation shard filename does not match from_id")
    source = objects.get(from_id)
    if source is None:
        return [f"unknown from_id {from_id}"]
    keys: set[tuple[str, str, str, str]] = set()
    for relation in document["relations"]:
        to_id = relation["to_id"]
        target = objects.get(to_id)
        if target is None:
            errors.append(f"unknown to_id {to_id}")
            continue
        relation_type = relation["relation_type"]
        allowed_from, allowed_to = RELATION_MATRIX[relation_type]
        if source["kind"] not in allowed_from or target["kind"] not in allowed_to:
            errors.append(f"invalid kind pair for {relation_type}")
        if relation_type == "summarizes" and source.get("note_type") != "literature":
            errors.append("summarizes must originate from a Literature Note")
        if relation_type == "synthesizes" and source.get("note_type") != "synthesis":
            errors.append("synthesizes must originate from a Synthesis Note")
        if relation_type == "snippet_from" and target.get("source_type") != "oss":
            errors.append("snippet_from must target an OSS Source")
        if relation_type == "supersedes" and source["kind"] != target["kind"]:
            errors.append("supersedes must target the same object kind")
        if relation_type == "related_to" and from_id >= to_id:
            errors.append("related_to is not stored in canonical ID order")
        section_id = relation.get("to_section_id", "")
        if section_id and section_id not in sections.get(to_id, set()):
            errors.append(f"unknown stable section {section_id}")
        locator_key = json.dumps(relation.get("locator", {}), sort_keys=True, separators=(",", ":"))
        key = (to_id, section_id, relation_type, locator_key)
        if key in keys:
            errors.append("duplicate canonical relation key")
        keys.add(key)
        if (
            relation_type in CONTENT_DEPENDENCIES
            and source["visibility"] == "public"
            and target["visibility"] == "private"
        ):
            errors.append("public object has a private content dependency")
    return errors


def relation_cardinality_errors(
    objects: dict[str, dict[str, Any]], relation_documents: list[dict[str, Any]]
) -> list[str]:
    by_from = {document["from_id"]: document["relations"] for document in relation_documents}
    errors: list[str] = []
    for object_id, data in objects.items():
        if data["kind"] != "note":
            continue
        relations = by_from.get(object_id, [])
        if data["note_type"] == "literature":
            summaries = [r for r in relations if r["relation_type"] == "summarizes"]
            if len(summaries) < 1:
                errors.append(f"{object_id}: Literature Note has no summarizes relation")
        if data["note_type"] == "synthesis" and (
            data["maturity"] in {"mature", "evergreen"} or data["visibility"] == "public"
        ):
            syntheses = [r for r in relations if r["relation_type"] == "synthesizes"]
            if len(syntheses) < 2:
                errors.append(f"{object_id}: mature/public Synthesis has fewer than two targets")
    return errors


def migration_report_semantic_errors(report: dict[str, Any]) -> list[str]:
    unresolved = [
        finding
        for finding in report["findings"]
        if finding["kind"] in {"decision", "blocker"} and finding["status"] == "unresolved"
    ]
    if report["apply_allowed"] and unresolved:
        return ["apply_allowed cannot be true with unresolved decisions or blockers"]
    return []
