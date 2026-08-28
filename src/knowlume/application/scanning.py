from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knowlume.adapters.contract_v2 import parse_object_document, parse_relation_shard
from knowlume.adapters.filesystem import checksum_file
from knowlume.domain.models import Note, NoteBody, ObjectDocument, RelationShard, Source
from knowlume.domain.validation import (
    validate_object_references,
    validate_relation_cardinality,
    validate_relation_shard,
)
from knowlume.domain.values import DomainError, ObjectId
from knowlume.ports.vault import Vault


@dataclass(frozen=True, order=True)
class Finding:
    sort_key: tuple[str, str, str, str] = field(init=False, repr=False)
    code: str
    severity: str
    category: str
    message: str
    path: str = ""
    object_id: str = ""
    section_id: str = ""
    details: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sort_key",
            (self.path, self.code, self.object_id, self.section_id),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "finding_version": 1,
            "code": self.code,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
        }
        for key in ("path", "object_id", "section_id"):
            if value := getattr(self, key):
                result[key] = value
        if self.details:
            result["details"] = self.details
        return result


@dataclass(frozen=True)
class ScannedObject:
    path: str
    checksum: str
    document: ObjectDocument


@dataclass(frozen=True)
class ScannedRelationShard:
    path: str
    checksum: str
    shard: RelationShard


@dataclass(frozen=True)
class ScanResult:
    objects: dict[ObjectId, ScannedObject]
    relation_shards: dict[ObjectId, ScannedRelationShard]
    findings: tuple[Finding, ...]
    files_scanned: int

    @property
    def healthy(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)

    def object_counts(self) -> dict[str, int]:
        counts = {"source": 0, "note": 0, "snippet": 0, "ai_artifact": 0}
        for scanned in self.objects.values():
            counts[scanned.document.object.id.kind.value] += 1
        return counts


def _category(code: str) -> str:
    if "PATH" in code or "UNSAFE" in code:
        return "security"
    if code.startswith("RELATION") or code.startswith(("LITERATURE", "SYNTHESIS")):
        return "relation"
    if code.startswith(("FACT", "AI_", "SNIPPET_SOURCE")) or "MISSING" in code:
        return "reference"
    if code.startswith(("FRONTMATTER", "FIELD", "SECTION", "NOTE_BLOCK")):
        return "parse"
    return "contract"


def _finding(
    error: DomainError,
    *,
    path: str = "",
    object_id: str = "",
    section_id: str = "",
) -> Finding:
    return Finding(
        code=error.code,
        severity="error",
        category=_category(error.code),
        message=str(error),
        path=path,
        object_id=object_id,
        section_id=section_id,
        details=error.details,
    )


def _relative(vault: Vault, path: Path) -> str:
    return path.relative_to(vault.root).as_posix()


def _safe_file(vault: Vault, path: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(vault.root)
    except (OSError, ValueError):
        return False
    return resolved.is_file()


def _expected_layout(vault: Vault, path: Path, document: ObjectDocument) -> DomainError | None:
    relative = path.relative_to(vault.root)
    obj = document.object
    if isinstance(obj, Source):
        expected = (
            Path(vault.config.sources)
            / {
                "paper": "papers",
                "web": "web",
                "book": "books",
                "oss": "oss",
            }[obj.source_type.value]
        )
    elif isinstance(obj, Note):
        note_root = Path(vault.config.notes)
        expected = (
            note_root
            / {
                "idea": "ideas",
                "literature": "literature",
                "concept": "concepts",
                "synthesis": "syntheses",
            }[obj.note_type.value]
        )
        if obj.note_type.value == "concept" and obj.type_history:
            if relative.is_relative_to(expected) or relative.is_relative_to(note_root / "ideas"):
                return None
    elif obj.id.kind.value == "snippet":
        expected = Path(vault.config.snippets)
    else:
        expected = Path(vault.config.ai_artifacts)
    try:
        relative.relative_to(expected)
    except ValueError:
        return DomainError(
            "OBJECT_LAYOUT_INVALID", "object kind or subtype does not match its path"
        )
    return None


def scan_vault(vault: Vault) -> ScanResult:
    findings: list[Finding] = []
    objects: dict[ObjectId, ScannedObject] = {}
    relation_shards: dict[ObjectId, ScannedRelationShard] = {}
    files_scanned = 0
    object_roots = (
        vault.path("sources"),
        vault.path("notes"),
        vault.path("snippets"),
        vault.path("ai_artifacts"),
    )
    object_paths = sorted(
        (path for root in object_roots for path in root.rglob("*") if path.is_file()),
        key=lambda path: _relative(vault, path),
    )
    for path in object_paths:
        relative = _relative(vault, path)
        files_scanned += 1
        if path.suffix.lower() != ".md":
            findings.append(
                _finding(
                    DomainError("OBJECT_LAYOUT_INVALID", "durable object must be Markdown"),
                    path=relative,
                )
            )
            continue
        if not _safe_file(vault, path):
            findings.append(
                _finding(
                    DomainError("VAULT_PATH_UNSAFE", "object path escapes the Vault"), path=relative
                )
            )
            continue
        try:
            document = parse_object_document(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            findings.append(
                _finding(DomainError("OBJECT_READ_FAILED", "object cannot be read"), path=relative)
            )
            continue
        except DomainError as error:
            findings.append(_finding(error, path=relative))
            continue
        object_id = document.object.id
        if object_id in objects:
            findings.append(
                _finding(
                    DomainError("OBJECT_ID_DUPLICATE", f"duplicate object ID {object_id}"),
                    path=relative,
                    object_id=str(object_id),
                )
            )
            continue
        layout_error = _expected_layout(vault, path, document)
        if layout_error:
            findings.append(_finding(layout_error, path=relative, object_id=str(object_id)))
        checksum = checksum_file(path)
        assert checksum is not None
        objects[object_id] = ScannedObject(relative, checksum, document)

    relation_root = vault.path("relations")
    relation_paths = sorted(
        (path for path in relation_root.rglob("*") if path.is_file()),
        key=lambda path: _relative(vault, path),
    )
    for path in relation_paths:
        relative = _relative(vault, path)
        files_scanned += 1
        if path.suffix.lower() != ".yaml" or path.parent != relation_root:
            findings.append(
                _finding(
                    DomainError(
                        "RELATION_LAYOUT_INVALID",
                        "relation shard must be relations/<from_id>.yaml",
                    ),
                    path=relative,
                )
            )
            continue
        if not _safe_file(vault, path):
            findings.append(
                _finding(
                    DomainError("VAULT_PATH_UNSAFE", "relation path escapes the Vault"),
                    path=relative,
                )
            )
            continue
        try:
            shard = parse_relation_shard(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            findings.append(
                _finding(
                    DomainError("RELATION_READ_FAILED", "relation shard cannot be read"),
                    path=relative,
                )
            )
            continue
        except DomainError as error:
            findings.append(_finding(error, path=relative))
            continue
        if shard.from_id in relation_shards:
            findings.append(
                _finding(
                    DomainError("RELATION_SHARD_DUPLICATE", "more than one shard owns from_id"),
                    path=relative,
                    object_id=str(shard.from_id),
                )
            )
            continue
        checksum = checksum_file(path)
        assert checksum is not None
        relation_shards[shard.from_id] = ScannedRelationShard(relative, checksum, shard)

    documents = {object_id: scanned.document for object_id, scanned in objects.items()}
    sections = {
        object_id: {str(section.section_id) for section in scanned.document.body.sections}
        for object_id, scanned in objects.items()
        if isinstance(scanned.document.body, NoteBody)
    }
    for object_id, scanned_object in objects.items():
        for validation_error in validate_object_references(scanned_object.document, documents):
            findings.append(
                _finding(
                    validation_error,
                    path=scanned_object.path,
                    object_id=str(object_id),
                )
            )
    for object_id, scanned_relation in relation_shards.items():
        for validation_error in validate_relation_shard(
            scanned_relation.shard,
            shard_name=Path(scanned_relation.path).stem,
            objects=documents,
            sections=sections,
        ):
            findings.append(
                _finding(
                    validation_error,
                    path=scanned_relation.path,
                    object_id=str(object_id),
                )
            )
    shards = {
        object_id: scanned_relation.shard for object_id, scanned_relation in relation_shards.items()
    }
    for validation_error in validate_relation_cardinality(documents, shards):
        related_id = str(validation_error).split(":", 1)[0]
        related_object = (
            objects.get(ObjectId(related_id)) if related_id.startswith("note_") else None
        )
        findings.append(
            _finding(
                validation_error,
                path=related_object.path if related_object else "",
                object_id=related_id,
            )
        )
    return ScanResult(objects, relation_shards, tuple(sorted(findings)), files_scanned)


def changed_paths(vault: Vault) -> set[str]:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(vault.root),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DomainError(
            "CHANGED_FILES_UNAVAILABLE", "Git changed-file detection is unavailable"
        ) from error
    if result.returncode != 0:
        raise DomainError("CHANGED_FILES_UNAVAILABLE", "Vault is not an available Git work tree")
    records = [record for record in result.stdout.decode(errors="replace").split("\0") if record]
    paths: set[str] = set()
    index = 0
    while index < len(records):
        record = records[index]
        status = record[:2]
        path = record[3:]
        paths.add(path.replace("\\", "/"))
        if "R" in status or "C" in status:
            index += 1
            if index < len(records):
                paths.add(records[index].replace("\\", "/"))
        index += 1
    return paths
