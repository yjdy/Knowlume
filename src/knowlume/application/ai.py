from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from knowlume.adapters.contract_v2 import (
    FRONTMATTER_RE,
    object_data,
    render_object_document,
)
from knowlume.adapters.filesystem import checksum_bytes, checksum_file, parse_vault_config
from knowlume.adapters.transactions import RecoverableTransactions
from knowlume.application.scanning import ScannedObject, ScanResult, scan_vault
from knowlume.domain.ai import (
    FileRevision,
    human_identity,
    safe_evidence_path,
    valid_checksum,
)
from knowlume.domain.models import (
    AIArtifact,
    FactBlock,
    NoteBody,
    ObjectDocument,
)
from knowlume.domain.values import (
    ArtifactType,
    DomainError,
    ObjectId,
    RecordStatus,
    RelationType,
    ReviewStatus,
    SectionId,
)
from knowlume.ports.vault import Vault

CONTENT_RELATIONS = {"cites", "derived_from", "summarizes", "synthesizes", "snippet_from"}


def artifact_digest(document: ObjectDocument) -> str:
    """Version-1 review digest, independent of review metadata and file formatting."""
    if not isinstance(document.object, AIArtifact) or not isinstance(document.body, str):
        raise DomainError("AI_ARTIFACT_NOT_FOUND", "an AI Artifact is required")
    data = object_data(document.object)
    for key in ("review_status", "reviewed_by", "reviewed_at", "review_evidence", "promotion"):
        data.pop(key, None)
    payload = {"object": data, "body": document.body.replace("\r\n", "\n").replace("\r", "\n")}
    return checksum_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    )


def _artifact(scan: ScanResult, value: str) -> ScannedObject:
    try:
        found = scan.objects.get(ObjectId(value))
    except DomainError as error:
        raise DomainError("AI_ARTIFACT_NOT_FOUND", "AI Artifact was not found") from error
    if found is None or not isinstance(found.document.object, AIArtifact):
        raise DomainError("AI_ARTIFACT_NOT_FOUND", "AI Artifact was not found")
    return found


def _expected(actual: str, expected: str) -> None:
    try:
        valid_checksum(expected)
    except DomainError as error:
        raise DomainError(
            "AI_ARGUMENT_INVALID", "expected checksum must be a sha256 revision token"
        ) from error
    if actual != expected:
        raise DomainError(
            "VAULT_WRITE_CONFLICT", "file changed since it was inspected; read its current revision"
        )


def _identity(value: str) -> str:
    try:
        return human_identity(value)
    except DomainError as error:
        raise DomainError(
            "AI_ARGUMENT_INVALID", "explicit human attribution is required"
        ) from error


def _safe_checksum(vault: Vault, relative: str) -> str | None:
    safe_evidence_path(relative)
    path = vault.root / relative
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(vault.root)
        # Even an in-Vault alias would permit two identities for one write target.
        if resolved != path.absolute():
            raise ValueError("alias")
        return checksum_file(path)
    except (OSError, ValueError) as error:
        raise DomainError(
            "VAULT_PATH_UNSAFE", "AI dependency path is unsafe or unreadable"
        ) from error


def _checked_bytes(vault: Vault, scanned: ScannedObject) -> bytes:
    if _safe_checksum(vault, scanned.path) != scanned.checksum:
        raise DomainError("VAULT_WRITE_CONFLICT", "file changed after scanning")
    content = (vault.root / scanned.path).read_bytes()
    _expected(checksum_bytes(content), scanned.checksum)
    return content


def _preserve_body(document: ObjectDocument, original: bytes, *, append: str = "") -> bytes:
    text = original.decode("utf-8")
    old = FRONTMATTER_RE.match(text)
    rendered = render_object_document(document)
    new = FRONTMATTER_RE.match(rendered)
    assert old is not None and new is not None
    linebreak = "\r\n" if "\r\n" in old.group(0) else "\n"
    header = rendered[: new.end()].replace("\n", linebreak)
    return (header + text[old.end() :] + append.replace("\n", linebreak)).encode("utf-8")


def _inventory(vault: Vault) -> set[str]:
    return {
        path.relative_to(vault.root).as_posix()
        for name in ("sources", "notes", "snippets", "ai_artifacts", "relations")
        for path in vault.path(name).rglob("*")
        if path.is_file()
    }


def _configuration_revision(vault: Vault) -> str:
    checksum = _safe_checksum(vault, "knowlume.toml")
    content = (vault.root / "knowlume.toml").read_bytes()
    if (
        checksum_bytes(content) != checksum
        or parse_vault_config(content.decode("utf-8")) != vault.config
    ):
        raise DomainError("AI_INPUT_CHANGED", "Vault configuration changed; rediscover it first")
    return checksum_bytes(content)


def _read_guard(
    vault: Vault, scan: ScanResult, configuration_checksum: str
) -> Callable[[Mapping[str, str]], None]:
    revisions: dict[str, str | None] = {item.path: item.checksum for item in scan.objects.values()}
    revisions.update({item.path: item.checksum for item in scan.relation_shards.values()})
    initial_inventory = set(revisions)
    revisions["knowlume.toml"] = configuration_checksum

    def verify(replacements: Mapping[str, str]) -> None:
        if _inventory(vault) != initial_inventory | set(replacements):
            raise DomainError("AI_INPUT_CHANGED", "Vault object inventory changed before commit")
        for path, checksum in (revisions | dict(replacements)).items():
            if _safe_checksum(vault, path) != checksum:
                raise DomainError("AI_INPUT_CHANGED", "a scanned dependency changed before commit")

    verify({})
    return verify


def _dependencies(
    vault: Vault, scan: ScanResult, artifact_id: ObjectId
) -> tuple[FileRevision, ...]:
    found: dict[str, str | None] = {}
    visited: set[ObjectId] = set()
    visiting: set[ObjectId] = set()
    superseded = {
        r.to_id
        for shard in scan.relation_shards.values()
        for r in shard.shard.relations
        if r.relation_type is RelationType.SUPERSEDES
    }

    def walk(object_id: ObjectId, section_id: SectionId | None = None) -> None:
        item = scan.objects.get(object_id)
        if (
            item is None
            or item.document.object.record_status is not RecordStatus.ACTIVE
            or object_id in superseded
        ):
            raise DomainError(
                "AI_INPUT_INVALID", "AI input must resolve to an active non-superseded object"
            )
        if section_id is not None and (
            not isinstance(item.document.body, NoteBody)
            or section_id not in {s.section_id for s in item.document.body.sections}
        ):
            raise DomainError("AI_INPUT_INVALID", "AI input section does not exist")
        if object_id in visiting:
            raise DomainError("AI_INPUT_INVALID", "AI input dependencies contain a cycle")
        if object_id in visited:
            return
        visiting.add(object_id)
        if object_id != artifact_id:
            found[item.path] = item.checksum
        shard = scan.relation_shards.get(object_id)
        shard_path = f"{vault.config.relations}/{object_id}.yaml"
        found[shard_path] = shard.checksum if shard else None
        obj = item.document.object
        if isinstance(obj, AIArtifact):
            if obj.prompt_ref is not None:
                safe_evidence_path(obj.prompt_ref)
                _safe_checksum_path_only(vault, obj.prompt_ref)
            for input_ref in obj.input_refs:
                walk(input_ref.object_id, input_ref.section_id)
        if isinstance(item.document.body, NoteBody):
            for section in item.document.body.sections:
                for block in section.blocks:
                    if isinstance(block, FactBlock):
                        for citation in block.citations:
                            walk(citation.source_id)
        if shard:
            for relation in shard.shard.relations:
                if relation.relation_type.value in CONTENT_RELATIONS:
                    walk(relation.to_id, relation.to_section_id)
        visiting.remove(object_id)
        visited.add(object_id)

    walk(artifact_id)
    return tuple(FileRevision(path, checksum) for path, checksum in sorted(found.items()))


def _safe_checksum_path_only(vault: Vault, relative: str) -> None:
    """Validate a prompt reference without opening or hashing the referenced file."""
    path = vault.root / safe_evidence_path(relative)
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(vault.root)
        if path.absolute() != resolved:
            raise ValueError("alias")
    except (ValueError, OSError) as error:
        raise DomainError(
            "VAULT_PATH_UNSAFE", "prompt reference resolves outside its safe location"
        ) from error


class AIService:
    def __init__(
        self,
        *,
        transactions: RecoverableTransactions | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._transactions = transactions or RecoverableTransactions()
        self._clock = clock

    def _scan(self, vault: Vault) -> ScanResult:
        scan = scan_vault(vault)
        if not scan.healthy:
            codes = {finding.code for finding in scan.findings}
            code = next(
                (
                    candidate
                    for candidate in (
                        "VAULT_PATH_UNSAFE",
                        "AI_REVIEW_EVIDENCE_UNSUPPORTED",
                        "AI_REVIEW_EVIDENCE_INVALID",
                    )
                    if candidate in codes
                ),
                "VAULT_INVALID",
            )
            raise DomainError(code, "Vault must pass scan before an AI workflow")
        return scan

    def list(
        self,
        vault: Vault,
        *,
        review_status: str = "unreviewed",
        artifact_type: str = "all",
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if (
            review_status not in {"all", *ReviewStatus}
            or artifact_type not in {"all", *ArtifactType}
            or status not in {"all", *RecordStatus}
            or not 1 <= limit <= 200
            or offset < 0
        ):
            raise DomainError("AI_ARGUMENT_INVALID", "invalid AI queue filters or bounds")
        scan = self._scan(vault)
        selected = []
        for item in scan.objects.values():
            obj = item.document.object
            if not isinstance(obj, AIArtifact):
                continue
            if (
                (review_status == "all" or obj.review_status.value == review_status)
                and (artifact_type == "all" or obj.artifact_type.value == artifact_type)
                and (status == "all" or obj.record_status.value == status)
            ):
                selected.append(item)
        selected.sort(key=lambda item: (item.document.object.created, str(item.document.object.id)))
        items = []
        for item in selected[offset : offset + limit]:
            obj = item.document.object
            assert isinstance(obj, AIArtifact)
            items.append(
                {
                    "object_id": str(obj.id),
                    "path": item.path,
                    "checksum": item.checksum,
                    "artifact_type": obj.artifact_type.value,
                    "title": obj.title,
                    "record_status": obj.record_status.value,
                    "review_status": obj.review_status.value,
                    "created": obj.created.isoformat(),
                    "generated_by": obj.generated_by,
                    "model": obj.model,
                    "reviewed_by": obj.reviewed_by,
                    "reviewed_at": obj.reviewed_at.isoformat() if obj.reviewed_at else None,
                    "evidence_version": obj.review_evidence.version
                    if obj.review_evidence
                    else None,
                }
            )
        return {
            "result_version": 1,
            "scope": "trusted-local",
            "filters": {"review_status": review_status, "type": artifact_type, "status": status},
            "limit": limit,
            "offset": offset,
            "total": len(selected),
            "items": items,
        }
