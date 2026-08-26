# ADR-0001: Files are the durable source of truth

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

Knowlume must preserve personal knowledge for years without depending on one editor, database schema, search engine, or AI product. Obsidian, Zotero, SQLite, Quartz, and future native components have different lifecycles and failure modes. Treating an application-private database as the only authority would make migration, inspection, recovery, and Git history fragile.

## Decision

Tracked Markdown/YAML files and stable references to original source material are the durable knowledge authority. SQLite is a rebuildable projection; caches, derived output, temporary clones, and public staging are disposable. Git records the evolution of tracked files.

The active storage and rebuild requirements are defined in [`../storage-index-search.md`](../storage-index-search.md). Executable object contracts live in [`../../schemas/`](../../schemas/README.md).

## Consequences

### Benefits

- Knowledge remains human-readable and recoverable without Knowlume running.
- Git diff and history expose ordinary knowledge evolution.
- Search/index implementations can be replaced or rebuilt.
- Editors and publishers remain adapters rather than data owners.

### Costs and constraints

- File parsing, schema migration, duplicate-ID detection, and atomic writes become core responsibilities.
- Cross-file integrity cannot rely on database foreign keys alone.
- Large attachments require a separate backup and recovery policy.
- Rebuild equivalence must be covered by executable tests.

## Alternatives considered

- SQLite as the primary database: rejected because it weakens portability and direct inspection.
- Obsidian internal state as authority: rejected because it couples the model to one editor.
- A remote cloud service as authority: rejected for the local-first v1 boundary.

## Revisit when

Revisit only if file-scale or transactional requirements cannot be met after measured implementation evidence. A future database may become an additional durable store only through an explicit migration ADR; it must not silently replace the file authority.
