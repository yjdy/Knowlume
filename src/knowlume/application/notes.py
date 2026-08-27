from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime

from knowlume.adapters.contract_v2 import (
    parse_object_document,
    render_object_document,
    render_relation_shard,
)
from knowlume.adapters.filesystem import FilesystemVault
from knowlume.adapters.transactions import RecoverableTransactions, WriteRequest
from knowlume.application.scanning import scan_vault
from knowlume.domain.models import Actor, Note, NoteBody, Relation, RelationShard, TypeTransition
from knowlume.domain.validation import (
    validate_object_references,
    validate_relation_cardinality,
    validate_relation_shard,
)
from knowlume.domain.values import (
    ActorType,
    DomainError,
    NoteType,
    ObjectId,
    RelationType,
    SectionRole,
    enum_value,
)
from knowlume.ids import new_ulid
from knowlume.ports.vault import Vault

TEMPLATE_BY_TYPE = {
    NoteType.IDEA: "templates/v2/notes/idea.md",
    NoteType.LITERATURE: "templates/v2/notes/literature.md",
    NoteType.CONCEPT: "templates/v2/notes/concept.md",
    NoteType.SYNTHESIS: "templates/v2/notes/synthesis.md",
}
FOLDER_BY_TYPE = {
    NoteType.IDEA: "ideas",
    NoteType.LITERATURE: "literature",
    NoteType.CONCEPT: "concepts",
    NoteType.SYNTHESIS: "syntheses",
}


class NoteService:
    def __init__(
        self,
        *,
        filesystem: FilesystemVault,
        template_reader: Callable[[str], str],
        transactions: RecoverableTransactions | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        ulid_factory: Callable[[], str] = new_ulid,
    ) -> None:
        self._filesystem = filesystem
        self._template_reader = template_reader
        self._transactions = transactions or RecoverableTransactions()
        self._clock = clock
        self._ulid_factory = ulid_factory

    def _healthy_scan(self, vault: Vault):  # type: ignore[no-untyped-def]
        result = scan_vault(vault)
        if not result.healthy:
            raise DomainError("VAULT_INVALID", "Vault must pass scan before Note mutation")
        return result

    def create(
        self, vault: Vault, note_type_value: str, *, source_id_value: str | None = None
    ) -> ObjectId:
        note_type = enum_value(NoteType, note_type_value, field="Note type")
        if note_type is NoteType.LITERATURE and source_id_value is None:
            raise DomainError("NOTE_SOURCE_REQUIRED", "Literature Note requires --source SOURCE_ID")
        if note_type is not NoteType.LITERATURE and source_id_value is not None:
            raise DomainError("NOTE_SOURCE_INVALID", "--source is only valid for Literature Notes")
        current = self._healthy_scan(vault)
        source_id = ObjectId(source_id_value) if source_id_value else None
        if source_id is not None:
            source = current.objects.get(source_id)
            if source is None or source.document.object.id.kind.value != "source":
                raise DomainError(
                    "NOTE_SOURCE_INVALID", "--source must reference an existing Source"
                )
        note_id = ObjectId(f"note_{self._ulid_factory()}")
        today = self._clock().date().isoformat()
        title = f"Untitled {note_type.value}"
        template = self._template_reader(TEMPLATE_BY_TYPE[note_type])
        rendered = (
            template.replace("note_<ULID>", str(note_id))
            .replace("<title>", title)
            .replace("<YYYY-MM-DD>", today)
        )
        document = parse_object_document(rendered)
        assert isinstance(document.object, Note)
        assert isinstance(document.body, NoteBody)
        documents = {object_id: scanned.document for object_id, scanned in current.objects.items()}
        documents[note_id] = document
        reference_errors = validate_object_references(document, documents)
        if reference_errors:
            raise reference_errors[0]
        shard: RelationShard | None = None
        shards = {
            object_id: scanned.shard for object_id, scanned in current.relation_shards.items()
        }
        if source_id is not None:
            now = self._clock()
            shard = RelationShard(
                note_id,
                (
                    Relation(
                        source_id,
                        RelationType.SUMMARIZES,
                        now,
                        Actor(ActorType.HUMAN, "cli-user"),
                    ),
                ),
            )
            sections = {
                object_id: {str(section.section_id) for section in scanned.document.body.sections}
                for object_id, scanned in current.objects.items()
                if isinstance(scanned.document.body, NoteBody)
            }
            sections[note_id] = {str(section.section_id) for section in document.body.sections}
            relation_errors = validate_relation_shard(
                shard,
                shard_name=str(note_id),
                objects=documents,
                sections=sections,
            )
            if relation_errors:
                raise relation_errors[0]
            shards[note_id] = shard
        cardinality_errors = validate_relation_cardinality(documents, shards)
        new_errors = [error for error in cardinality_errors if str(note_id) in str(error)]
        if new_errors:
            raise new_errors[0]
        relative = f"{vault.config.notes}/{FOLDER_BY_TYPE[note_type]}/{note_id}.md"
        content = render_object_document(document).encode()
        if shard is None:
            self._filesystem.atomic_write(vault, relative, content, None)
        else:
            relation_path = f"{vault.config.relations}/{note_id}.yaml"
            self._transactions.commit(
                vault,
                "relation-update",
                (
                    WriteRequest(relative, content, None),
                    WriteRequest(relation_path, render_relation_shard(shard).encode(), None),
                ),
            )
        if not scan_vault(vault).healthy:
            raise DomainError("VAULT_INVALID", "created Note did not pass scanner validation")
        return note_id

    def show(self, vault: Vault, object_id_value: str) -> str:
        object_id = ObjectId(object_id_value)
        result = self._healthy_scan(vault)
        scanned = result.objects.get(object_id)
        if scanned is None or not isinstance(scanned.document.object, Note):
            raise DomainError("NOTE_NOT_FOUND", "Note ID does not exist")
        return render_object_document(scanned.document)

    def evolve(self, vault: Vault, object_id_value: str, target_value: str) -> ObjectId:
        object_id = ObjectId(object_id_value)
        target = enum_value(NoteType, target_value, field="evolution target")
        if target is not NoteType.CONCEPT:
            raise DomainError("NOTE_TRANSITION_INVALID", "only --to concept is supported")
        result = self._healthy_scan(vault)
        scanned = result.objects.get(object_id)
        if scanned is None or not isinstance(scanned.document.object, Note):
            raise DomainError("NOTE_NOT_FOUND", "Note ID does not exist")
        note = scanned.document.object
        if note.note_type is not NoteType.IDEA:
            raise DomainError("NOTE_TRANSITION_INVALID", "only an Idea may evolve to Concept")
        changed_at = self._clock()
        transition = TypeTransition(
            NoteType.IDEA,
            NoteType.CONCEPT,
            changed_at,
            Actor(ActorType.HUMAN, "cli-user"),
        )
        evolved = replace(
            note,
            note_type=NoteType.CONCEPT,
            updated=date.fromisoformat(changed_at.date().isoformat()),
            type_history=note.type_history + (transition,),
        )
        assert isinstance(scanned.document.body, NoteBody)
        original_sections = tuple(
            (section.section_id, section.role, section.heading, section.blocks)
            for section in scanned.document.body.sections
        )
        document = replace(scanned.document, object=evolved)
        reparsed = parse_object_document(render_object_document(document))
        assert isinstance(reparsed.body, NoteBody)
        new_sections = tuple(
            (section.section_id, section.role, section.heading, section.blocks)
            for section in reparsed.body.sections
        )
        if original_sections != new_sections or not any(
            section.role is SectionRole.HUMAN for section in reparsed.body.sections
        ):
            raise DomainError("NOTE_TRANSITION_INVALID", "evolution changed Note sections")
        self._filesystem.atomic_write(
            vault,
            scanned.path,
            render_object_document(reparsed).encode(),
            scanned.checksum,
        )
        if not scan_vault(vault).healthy:
            raise DomainError("VAULT_INVALID", "evolved Note did not pass scanner validation")
        return object_id
