from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from knowlume.adapters.contract_v2 import (
    FRONTMATTER_RE,
    object_data,
    parse_object_document,
    render_object_document,
    render_relation_shard,
)
from knowlume.adapters.filesystem import checksum_bytes, checksum_file, parse_vault_config
from knowlume.adapters.transactions import RecoverableTransactions, WriteRequest
from knowlume.application.scanning import ScannedObject, ScanResult, scan_vault
from knowlume.domain.ai import (
    FileRevision,
    PromotionEvidence,
    ReviewAttribution,
    ReviewEvidence,
    human_identity,
    safe_evidence_path,
    valid_checksum,
)
from knowlume.domain.models import (
    Actor,
    AIArtifact,
    AIBlock,
    FactBlock,
    Note,
    NoteBody,
    ObjectDocument,
    Relation,
    RelationShard,
    Snippet,
)
from knowlume.domain.validation import (
    validate_object_references,
    validate_relation_cardinality,
    validate_relation_shard,
)
from knowlume.domain.values import (
    ActorType,
    ArtifactType,
    DomainError,
    ObjectId,
    RecordStatus,
    RelationType,
    ReviewStatus,
    SectionId,
    SectionRole,
    Visibility,
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
        if isinstance(obj, Snippet):
            walk(obj.source_id)
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

    def _verify_review(
        self, vault: Vault, scan: ScanResult, item: ScannedObject, *, inputs: bool = True
    ) -> None:
        obj = item.document.object
        assert isinstance(obj, AIArtifact)
        evidence = obj.review_evidence
        if evidence is None or evidence.content_checksum != artifact_digest(item.document):
            raise DomainError(
                "AI_REVIEW_EVIDENCE_INVALID",
                "review evidence is absent or candidate content changed",
            )
        if inputs and evidence.dependencies != _dependencies(vault, scan, obj.id):
            raise DomainError(
                "AI_INPUT_CHANGED", "reviewed input revisions changed; create a new candidate"
            )

    def review(
        self,
        vault: Vault,
        artifact_id: str,
        *,
        decision: str,
        reviewer: str,
        expected_checksum: str,
    ) -> dict[str, Any]:
        reviewer = _identity(reviewer)
        if decision not in {"accepted", "rejected"}:
            raise DomainError("AI_ARGUMENT_INVALID", "review decision must be accepted or rejected")
        configuration_checksum = _configuration_revision(vault)
        scan = self._scan(vault)
        guard = _read_guard(vault, scan, configuration_checksum)
        item = _artifact(scan, artifact_id)
        _expected(item.checksum, expected_checksum)
        obj = item.document.object
        assert isinstance(obj, AIArtifact)
        dependencies = _dependencies(vault, scan, obj.id)
        if obj.review_status is ReviewStatus.PROMOTED or (
            obj.review_status is not ReviewStatus.UNREVIEWED and obj.review_status.value != decision
        ):
            raise DomainError("AI_STATE_INVALID", "review transition is not allowed")
        if obj.review_evidence is not None:
            self._verify_review(vault, scan, item)
            if obj.reviewed_by != reviewer:
                raise DomainError("AI_STATE_INVALID", "review retry cannot change the reviewer")
            guard({})
            return self._review_result(obj, item.path, item.checksum, False)
        if obj.review_status is ReviewStatus.REJECTED:
            raise DomainError("AI_REVIEW_EVIDENCE_INVALID", "legacy rejected Artifact is read-only")
        now = self._clock()
        prior = (
            ReviewAttribution(obj.reviewed_by, obj.reviewed_at)
            if obj.reviewed_by and obj.reviewed_at
            else None
        )
        evidence = ReviewEvidence(
            1, artifact_digest(item.document), decision, reviewer, now, dependencies, prior
        )
        reviewed = replace(
            obj,
            review_status=ReviewStatus(decision),
            reviewed_by=reviewer,
            reviewed_at=now,
            review_evidence=evidence,
        )
        content = _preserve_body(
            replace(item.document, object=reviewed), _checked_bytes(vault, item)
        )
        parse_object_document(content.decode("utf-8"))
        (checksum,) = self._transactions.commit(
            vault,
            "ai-review",
            (WriteRequest(item.path, content, item.checksum),),
            validate_reads=guard,
        )
        return self._review_result(reviewed, item.path, checksum, True)

    @staticmethod
    def _review_result(obj: AIArtifact, path: str, checksum: str, changed: bool) -> dict[str, Any]:
        assert obj.reviewed_at is not None
        return {
            "result_version": 1,
            "artifact_id": str(obj.id),
            "path": path,
            "checksum": checksum,
            "review_status": obj.review_status.value,
            "reviewed_by": obj.reviewed_by,
            "reviewed_at": obj.reviewed_at.isoformat(),
            "changed": changed,
            "evidence_version": 1,
        }

    def promote(
        self,
        vault: Vault,
        artifact_id: str,
        *,
        note_id: str,
        section_id: str,
        actor: str,
        expected_artifact_checksum: str,
        expected_note_checksum: str,
        apply: bool = False,
    ) -> dict[str, Any]:
        actor = _identity(actor)
        try:
            target_id, section = ObjectId(note_id), SectionId(section_id)
        except DomainError as error:
            raise DomainError(
                "AI_ARGUMENT_INVALID", "target or section identity is invalid"
            ) from error
        configuration_checksum = _configuration_revision(vault)
        scan = self._scan(vault)
        guard = _read_guard(vault, scan, configuration_checksum)
        item = _artifact(scan, artifact_id)
        obj = item.document.object
        assert isinstance(obj, AIArtifact) and isinstance(item.document.body, str)
        note_item = scan.objects.get(target_id)
        if (
            note_item is None
            or not isinstance(note_item.document.object, Note)
            or not isinstance(note_item.document.body, NoteBody)
        ):
            raise DomainError("AI_TARGET_INVALID", "promotion target must be an existing Note")
        note = note_item.document.object
        _expected(item.checksum, expected_artifact_checksum)
        _expected(note_item.checksum, expected_note_checksum)
        if (
            note.visibility is not Visibility.PRIVATE
            or note.record_status is not RecordStatus.ACTIVE
            or obj.record_status is not RecordStatus.ACTIVE
        ):
            raise DomainError("AI_TARGET_INVALID", "promotion requires active private objects")
        if any(
            r.relation_type is RelationType.SUPERSEDES and r.to_id in {target_id, obj.id}
            for shard in scan.relation_shards.values()
            for r in shard.shard.relations
        ):
            raise DomainError("AI_TARGET_INVALID", "superseded objects cannot be promoted")
        existing = scan.relation_shards.get(target_id)
        relation_path = f"{vault.config.relations}/{target_id}.yaml"
        body = item.document.body
        if obj.review_status is ReviewStatus.PROMOTED:
            self._verify_review(vault, scan, item, inputs=False)
            proof = obj.promotion
            if (
                proof is None
                or (proof.note_id, proof.section_id, proof.actor_id) != (target_id, section, actor)
                or proof.note_checksum != note_item.checksum
                or existing is None
                or proof.relation_checksum != existing.checksum
            ):
                raise DomainError(
                    "AI_PROMOTION_CONFLICT",
                    "completed promotion does not match this request or current result",
                )
            matching = [s for s in note_item.document.body.sections if s.section_id == section]
            if (
                len(matching) != 1
                or matching[0].role is not SectionRole.AI
                or matching[0].blocks != (AIBlock(body, obj.id),)
                or not any(
                    r.to_id == obj.id
                    and r.relation_type is RelationType.PROMOTED_FROM
                    and r.actor == Actor(ActorType.HUMAN, actor)
                    and r.created_at == proof.promoted_at
                    for r in existing.shard.relations
                )
            ):
                raise DomainError(
                    "AI_PROMOTION_CONFLICT", "promotion content or audit relation changed"
                )
            guard({})
            return self._promotion_result(
                obj, item.path, note_item.path, relation_path, apply, False, True, body
            )
        if obj.review_status is not ReviewStatus.ACCEPTED:
            raise DomainError("AI_STATE_INVALID", "only an accepted Artifact can be promoted")
        self._verify_review(vault, scan, item)
        if any(s.section_id == section for s in note_item.document.body.sections):
            raise DomainError("AI_PROMOTION_CONFLICT", "target section already exists")
        if not body.strip() or re.search(r"<!--\s*knowlume\s*:", body, re.IGNORECASE):
            raise DomainError(
                "AI_CONTENT_UNSAFE",
                "candidate contains empty content or reserved structural metadata",
            )
        now = self._clock()
        append = (
            f"\n\n<!-- knowlume:section id={section} role=ai -->\n## Reviewed AI\n\n"
            f"<!-- knowlume:ai\nartifact_id: {obj.id}\n-->\n{body}\n"
        )
        note_document = replace(note_item.document, object=replace(note, updated=now.date()))
        note_content = _preserve_body(
            note_document, _checked_bytes(vault, note_item), append=append
        )
        reparsed = parse_object_document(note_content.decode("utf-8"))
        assert isinstance(reparsed.body, NoteBody)
        if (
            reparsed.body.sections[:-1] != note_item.document.body.sections
            or reparsed.body.sections[-1].blocks != (AIBlock(body, obj.id),)
            or reparsed.body.sections[-1].role is not SectionRole.AI
        ):
            raise DomainError("AI_CONTENT_UNSAFE", "candidate failed faithful AI-only round-trip")
        relations = list(existing.shard.relations) if existing else []
        candidate = Relation(obj.id, RelationType.PROMOTED_FROM, now, Actor(ActorType.HUMAN, actor))
        if any(r.canonical_key == candidate.canonical_key for r in relations):
            raise DomainError(
                "AI_PROMOTION_CONFLICT",
                "an audit relation already exists without matching promotion",
            )
        relations.append(candidate)
        relations.sort(key=lambda r: r.canonical_key)
        shard = RelationShard(target_id, tuple(relations))
        relation_content = render_relation_shard(shard).encode("utf-8")
        proof = PromotionEvidence(
            1,
            target_id,
            section,
            actor,
            now,
            checksum_bytes(note_content),
            checksum_bytes(relation_content),
        )
        promoted = replace(obj, review_status=ReviewStatus.PROMOTED, promotion=proof)
        artifact_document = replace(item.document, object=promoted)
        artifact_content = _preserve_body(artifact_document, _checked_bytes(vault, item))
        parse_object_document(artifact_content.decode("utf-8"))
        documents = {key: value.document for key, value in scan.objects.items()} | {
            target_id: reparsed,
            obj.id: artifact_document,
        }
        sections = {
            key: {str(s.section_id) for s in value.body.sections}
            for key, value in documents.items()
            if isinstance(value.body, NoteBody)
        }
        errors = [
            error
            for document in documents.values()
            for error in validate_object_references(document, documents)
        ]
        errors.extend(
            validate_relation_shard(
                shard, shard_name=str(target_id), objects=documents, sections=sections
            )
        )
        errors.extend(
            validate_relation_cardinality(
                documents,
                {key: value.shard for key, value in scan.relation_shards.items()}
                | {target_id: shard},
            )
        )
        if errors:
            raise DomainError("AI_TARGET_INVALID", "candidate object graph failed validation")
        writes = (
            WriteRequest(item.path, artifact_content, item.checksum),
            WriteRequest(note_item.path, note_content, note_item.checksum),
            WriteRequest(relation_path, relation_content, existing.checksum if existing else None),
        )
        guard({})
        if apply:
            self._transactions.commit(vault, "ai-promote", writes, validate_reads=guard)
        return self._promotion_result(
            promoted, item.path, note_item.path, relation_path, apply, apply, False, body
        )

    @staticmethod
    def _promotion_result(
        obj: AIArtifact,
        artifact_path: str,
        note_path: str,
        relation_path: str,
        apply: bool,
        changed: bool,
        already: bool,
        body: str,
    ) -> dict[str, Any]:
        assert obj.promotion is not None
        return {
            "result_version": 1,
            "artifact_id": str(obj.id),
            "note_id": str(obj.promotion.note_id),
            "section_id": str(obj.promotion.section_id),
            "mode": "apply" if apply else "dry-run",
            "changed": changed,
            "already_promoted": already,
            "files": [artifact_path, note_path, relation_path],
            "preview": {"heading": "Reviewed AI", "text": body, "artifact_id": str(obj.id)},
            "promotion": object_data(obj)["promotion"],
        }
