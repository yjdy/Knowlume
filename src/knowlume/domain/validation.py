from __future__ import annotations

from collections.abc import Mapping

from knowlume.domain.models import (
    AIArtifact,
    AIBlock,
    FactBlock,
    Note,
    NoteBody,
    ObjectDocument,
    RelationShard,
    Snippet,
    Source,
)
from knowlume.domain.values import (
    DomainError,
    NoteType,
    ObjectId,
    ObjectKind,
    RelationType,
    ReviewStatus,
    SourceType,
)

RELATION_MATRIX: dict[RelationType, tuple[set[ObjectKind], set[ObjectKind]]] = {
    RelationType.CITES: ({ObjectKind.NOTE}, {ObjectKind.SOURCE}),
    RelationType.SUMMARIZES: ({ObjectKind.NOTE}, {ObjectKind.SOURCE}),
    RelationType.SYNTHESIZES: ({ObjectKind.NOTE}, {ObjectKind.SOURCE, ObjectKind.NOTE}),
    RelationType.SUPPORTS: ({ObjectKind.SOURCE, ObjectKind.NOTE}, {ObjectKind.NOTE}),
    RelationType.CONTRADICTS: ({ObjectKind.SOURCE, ObjectKind.NOTE}, {ObjectKind.NOTE}),
    RelationType.RELATED_TO: ({ObjectKind.NOTE}, {ObjectKind.NOTE}),
    RelationType.SNIPPET_FROM: ({ObjectKind.SNIPPET}, {ObjectKind.SOURCE}),
    RelationType.DERIVED_FROM: (
        {ObjectKind.NOTE, ObjectKind.AI_ARTIFACT},
        {ObjectKind.SOURCE, ObjectKind.NOTE},
    ),
    RelationType.PROMOTED_FROM: ({ObjectKind.NOTE}, {ObjectKind.AI_ARTIFACT}),
    RelationType.SUPERSEDES: (
        {ObjectKind.SOURCE, ObjectKind.NOTE, ObjectKind.SNIPPET, ObjectKind.AI_ARTIFACT},
        {ObjectKind.SOURCE, ObjectKind.NOTE, ObjectKind.SNIPPET, ObjectKind.AI_ARTIFACT},
    ),
}
CONTENT_DEPENDENCIES = {
    RelationType.CITES,
    RelationType.SUMMARIZES,
    RelationType.SYNTHESIZES,
    RelationType.SUPPORTS,
    RelationType.CONTRADICTS,
    RelationType.SNIPPET_FROM,
    RelationType.DERIVED_FROM,
}


def validate_object_references(
    document: ObjectDocument, objects: Mapping[ObjectId, ObjectDocument]
) -> tuple[DomainError, ...]:
    errors: list[DomainError] = []
    obj = document.object
    if isinstance(obj, Snippet):
        target = objects.get(obj.source_id)
        if (
            target is None
            or not isinstance(target.object, Source)
            or target.object.source_type is not SourceType.OSS
        ):
            errors.append(
                DomainError(
                    "SNIPPET_SOURCE_INVALID", "Snippet source must be an existing OSS Source"
                )
            )
    if isinstance(obj, Note) and isinstance(document.body, NoteBody):
        for section in document.body.sections:
            for block in section.blocks:
                if isinstance(block, FactBlock):
                    for citation in block.citations:
                        target = objects.get(citation.source_id)
                        if target is None or not isinstance(target.object, Source):
                            errors.append(
                                DomainError(
                                    "FACT_SOURCE_MISSING", f"unknown Source {citation.source_id}"
                                )
                            )
                        elif (
                            citation.locator.__class__.__name__.removesuffix("Locator").lower()
                            != target.object.source_type.value
                        ):
                            errors.append(
                                DomainError(
                                    "FACT_LOCATOR_MISMATCH",
                                    "fact locator source type does not match Source",
                                )
                            )
                elif isinstance(block, AIBlock):
                    target = objects.get(block.artifact_id)
                    if target is None or not isinstance(target.object, AIArtifact):
                        errors.append(
                            DomainError(
                                "AI_ARTIFACT_MISSING", "AI block references an unknown Artifact"
                            )
                        )
                    elif target.object.review_status is not ReviewStatus.PROMOTED:
                        errors.append(
                            DomainError(
                                "AI_ARTIFACT_UNPROMOTED",
                                "AI block references an unpromoted Artifact",
                            )
                        )
    if isinstance(obj, AIArtifact):
        for input_ref in obj.input_refs:
            target = objects.get(input_ref.object_id)
            if target is None:
                errors.append(
                    DomainError("AI_INPUT_MISSING", f"unknown AI input {input_ref.object_id}")
                )
            elif input_ref.section_id is not None and (
                not isinstance(target.body, NoteBody)
                or input_ref.section_id
                not in {section.section_id for section in target.body.sections}
            ):
                errors.append(
                    DomainError(
                        "AI_INPUT_SECTION_MISSING",
                        f"unknown AI input section {input_ref.section_id}",
                    )
                )
    return tuple(errors)


def validate_relation_shard(
    shard: RelationShard,
    *,
    shard_name: str,
    objects: Mapping[ObjectId, ObjectDocument],
    sections: Mapping[ObjectId, set[str]],
) -> tuple[DomainError, ...]:
    errors: list[DomainError] = []
    if shard_name != str(shard.from_id):
        errors.append(
            DomainError(
                "RELATION_SHARD_OWNER_MISMATCH", "relation shard filename does not match from_id"
            )
        )
    source_document = objects.get(shard.from_id)
    if source_document is None:
        return (DomainError("RELATION_SOURCE_MISSING", f"unknown from_id {shard.from_id}"),)
    keys: set[tuple[str, str, str, str]] = set()
    for relation in shard.relations:
        target_document = objects.get(relation.to_id)
        if target_document is None:
            errors.append(DomainError("RELATION_TARGET_MISSING", f"unknown to_id {relation.to_id}"))
            continue
        source, target = source_document.object, target_document.object
        allowed_from, allowed_to = RELATION_MATRIX[relation.relation_type]
        if source.id.kind not in allowed_from or target.id.kind not in allowed_to:
            errors.append(
                DomainError(
                    "RELATION_KIND_INVALID", f"invalid kind pair for {relation.relation_type.value}"
                )
            )
        if relation.relation_type is RelationType.SUMMARIZES and (
            not isinstance(source, Note) or source.note_type is not NoteType.LITERATURE
        ):
            errors.append(
                DomainError(
                    "RELATION_DIRECTION_INVALID", "summarizes must originate from a Literature Note"
                )
            )
        if relation.relation_type is RelationType.SYNTHESIZES and (
            not isinstance(source, Note) or source.note_type is not NoteType.SYNTHESIS
        ):
            errors.append(
                DomainError(
                    "RELATION_DIRECTION_INVALID", "synthesizes must originate from a Synthesis Note"
                )
            )
        if relation.relation_type is RelationType.SNIPPET_FROM and (
            not isinstance(target, Source) or target.source_type is not SourceType.OSS
        ):
            errors.append(
                DomainError("RELATION_TARGET_INVALID", "snippet_from must target an OSS Source")
            )
        if (
            relation.relation_type is RelationType.SUPERSEDES
            and source.id.kind is not target.id.kind
        ):
            errors.append(
                DomainError("RELATION_KIND_INVALID", "supersedes must target the same object kind")
            )
        if relation.relation_type is RelationType.RELATED_TO and str(shard.from_id) >= str(
            relation.to_id
        ):
            errors.append(
                DomainError(
                    "RELATION_NOT_CANONICAL", "related_to is not stored in canonical ID order"
                )
            )
        if relation.to_section_id and str(relation.to_section_id) not in sections.get(
            relation.to_id, set()
        ):
            errors.append(
                DomainError(
                    "RELATION_SECTION_MISSING", f"unknown stable section {relation.to_section_id}"
                )
            )
        if (
            relation.locator is not None
            and isinstance(target, Source)
            and relation.locator.__class__.__name__.removesuffix("Locator").lower()
            != target.source_type.value
        ):
            errors.append(
                DomainError(
                    "RELATION_LOCATOR_MISMATCH",
                    "relation locator source type does not match target Source",
                )
            )
        if (
            relation.relation_type in CONTENT_DEPENDENCIES
            and source.visibility.value == "public"
            and target.visibility.value == "private"
        ):
            errors.append(
                DomainError(
                    "RELATION_PRIVATE_DEPENDENCY",
                    "public object has a private content dependency",
                )
            )
        if relation.canonical_key in keys:
            errors.append(DomainError("RELATION_DUPLICATE", "duplicate canonical relation key"))
        keys.add(relation.canonical_key)
    return tuple(errors)


def validate_relation_cardinality(
    objects: Mapping[ObjectId, ObjectDocument], relation_shards: Mapping[ObjectId, RelationShard]
) -> tuple[DomainError, ...]:
    errors: list[DomainError] = []
    for object_id, document in objects.items():
        if not isinstance(document.object, Note):
            continue
        relations = relation_shards.get(object_id, RelationShard(object_id, ())).relations
        if document.object.note_type is NoteType.LITERATURE and not any(
            r.relation_type is RelationType.SUMMARIZES for r in relations
        ):
            errors.append(
                DomainError(
                    "LITERATURE_SUMMARY_MISSING",
                    f"{object_id}: Literature Note has no summarizes relation",
                )
            )
        if (
            document.object.note_type is NoteType.SYNTHESIS
            and (
                document.object.maturity.value in {"mature", "evergreen"}
                or document.object.visibility.value == "public"
            )
            and sum(r.relation_type is RelationType.SYNTHESIZES for r in relations) < 2
        ):
            errors.append(
                DomainError(
                    "SYNTHESIS_TARGETS_INSUFFICIENT",
                    f"{object_id}: mature/public Synthesis has fewer than two targets",
                )
            )
    return tuple(errors)
