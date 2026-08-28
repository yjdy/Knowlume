from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from knowlume.adapters.contract_v2 import render_relation_shard
from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.domain.models import Actor, NoteBody, Relation, RelationShard
from knowlume.domain.validation import validate_relation_shard
from knowlume.domain.values import (
    ActorType,
    DomainError,
    ObjectId,
    RelationType,
    SectionId,
    enum_value,
)
from knowlume.ports.vault import Vault

CARDINALITY_CODES = {"LITERATURE_SUMMARY_MISSING", "SYNTHESIS_TARGETS_INSUFFICIENT"}


@dataclass(frozen=True, order=True)
class ListedRelation:
    direction: str
    from_id: ObjectId
    to_id: ObjectId
    relation_type: RelationType
    to_section_id: SectionId | None = None


class RelationService:
    def __init__(
        self,
        *,
        filesystem: FilesystemVault,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._filesystem = filesystem
        self._clock = clock

    def _catalog(self, vault: Vault) -> ScanResult:
        result = scan_vault(vault)
        blocking = [finding for finding in result.findings if finding.code not in CARDINALITY_CODES]
        if blocking:
            raise DomainError("VAULT_INVALID", "Vault has blocking findings for relation mutation")
        return result

    def _canonical_endpoints(
        self, from_id: ObjectId, to_id: ObjectId, relation_type: RelationType
    ) -> tuple[ObjectId, ObjectId]:
        if relation_type is RelationType.RELATED_TO and str(from_id) > str(to_id):
            return to_id, from_id
        return from_id, to_id

    def add(
        self,
        vault: Vault,
        from_value: str,
        to_value: str,
        relation_type_value: str,
        *,
        to_section_value: str | None = None,
    ) -> ListedRelation:
        requested_from = ObjectId(from_value)
        requested_to = ObjectId(to_value)
        relation_type = enum_value(RelationType, relation_type_value, field="relation type")
        from_id, to_id = self._canonical_endpoints(requested_from, requested_to, relation_type)
        section_id = SectionId(to_section_value) if to_section_value else None
        result = self._catalog(vault)
        if from_id not in result.objects or to_id not in result.objects:
            raise DomainError("RELATION_ENDPOINT_MISSING", "relation endpoint does not exist")
        existing = result.relation_shards.get(from_id)
        relations = list(existing.shard.relations) if existing else []
        candidate = Relation(
            to_id,
            relation_type,
            self._clock(),
            Actor(ActorType.HUMAN, "cli-user"),
            to_section_id=section_id,
        )
        if any(relation.canonical_key == candidate.canonical_key for relation in relations):
            raise DomainError("RELATION_ALREADY_EXISTS", "canonical relation already exists")
        relations.append(candidate)
        relations.sort(key=lambda relation: relation.canonical_key)
        shard = RelationShard(from_id, tuple(relations))
        documents = {object_id: scanned.document for object_id, scanned in result.objects.items()}
        sections = {
            object_id: {str(section.section_id) for section in scanned.document.body.sections}
            for object_id, scanned in result.objects.items()
            if isinstance(scanned.document.body, NoteBody)
        }
        errors = validate_relation_shard(
            shard,
            shard_name=str(from_id),
            objects=documents,
            sections=sections,
        )
        if errors:
            raise errors[0]
        relative = f"{vault.config.relations}/{from_id}.yaml"
        expected = existing.checksum if existing else None
        self._filesystem.atomic_write(
            vault, relative, render_relation_shard(shard).encode(), expected
        )
        return ListedRelation("outgoing", from_id, to_id, relation_type, section_id)

    def remove(
        self,
        vault: Vault,
        from_value: str,
        to_value: str,
        relation_type_value: str,
        *,
        to_section_value: str | None = None,
    ) -> ListedRelation:
        requested_from = ObjectId(from_value)
        requested_to = ObjectId(to_value)
        relation_type = enum_value(RelationType, relation_type_value, field="relation type")
        from_id, to_id = self._canonical_endpoints(requested_from, requested_to, relation_type)
        section_id = SectionId(to_section_value) if to_section_value else None
        result = self._catalog(vault)
        existing = result.relation_shards.get(from_id)
        if existing is None:
            raise DomainError("RELATION_NOT_FOUND", "relation shard does not exist")
        key = Relation(
            to_id,
            relation_type,
            self._clock(),
            Actor(ActorType.HUMAN, "cli-user"),
            to_section_id=section_id,
        ).canonical_key
        matches = [
            relation for relation in existing.shard.relations if relation.canonical_key == key
        ]
        if len(matches) != 1:
            raise DomainError("RELATION_NOT_FOUND", "canonical relation does not exist")
        relations = tuple(
            relation for relation in existing.shard.relations if relation.canonical_key != key
        )
        shard = RelationShard(from_id, relations)
        relative = f"{vault.config.relations}/{from_id}.yaml"
        self._filesystem.atomic_write(
            vault,
            relative,
            render_relation_shard(shard).encode(),
            existing.checksum,
        )
        return ListedRelation("outgoing", from_id, to_id, relation_type, section_id)

    def list(self, vault: Vault, object_id_value: str) -> tuple[ListedRelation, ...]:
        object_id = ObjectId(object_id_value)
        result = self._catalog(vault)
        if object_id not in result.objects:
            raise DomainError("RELATION_ENDPOINT_MISSING", "object ID does not exist")
        listed: list[ListedRelation] = []
        for from_id, scanned in result.relation_shards.items():
            for relation in scanned.shard.relations:
                if from_id == object_id:
                    listed.append(
                        ListedRelation(
                            "outgoing",
                            from_id,
                            relation.to_id,
                            relation.relation_type,
                            relation.to_section_id,
                        )
                    )
                if relation.to_id == object_id:
                    listed.append(
                        ListedRelation(
                            "incoming",
                            from_id,
                            relation.to_id,
                            relation.relation_type,
                            relation.to_section_id,
                        )
                    )
        return tuple(sorted(listed))
