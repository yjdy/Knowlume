# ADR-0007: Relations are sharded by source object

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

Contract v1 duplicated durable links across Note frontmatter and a global relation collection. A single collection also creates an unnecessary write-conflict hotspot.

## Decision

Contract v2 stores each relation collection at `relations/<from_id>.yaml`. The document declares `from_id`; entries contain targets, relation semantics, creation time, and a structured actor. Note frontmatter no longer stores `source_ids`, `related_notes`, or supersession links.

Semantic validation owns the allowed kind matrix, stable-section integrity, canonical uniqueness, same-kind supersession, and canonical storage of symmetric `related_to` relations. AI output may propose relations only as private AI Artifacts; a trusted relation requires a human or deterministic system action.

## Consequences

- Backlinks and inverse relations are derived by scanning or indexing.
- File ownership and conflict scope are clear.
- Migration can mechanically split v1 collections, while ambiguous Note-level source semantics remain review items.

## Alternatives considered

- Keep a global relation file: rejected because it centralizes conflicts.
- Keep frontmatter and relation files in sync: rejected because it creates two authorities.

