# Contract v2 schemas

Contract v2 is the production target after Phase 0R.

- `objects.schema.json`: Source, Note, Snippet, and AI Artifact frontmatter, including compatible
  Phase 2A Paper/arXiv, Zotero synchronization, primary-PDF integrity fields, and optional Book
  edition metadata. Existing Web Sources without `snapshot_ref` remain readable.
- `note-body.schema.json`: normalized role-based Note body.
- `locator.schema.json`: paper, web snapshot, book, and OSS locators.
- `relations.schema.json`: one relation shard per source object.
- `sqlite-projection-v2.sql`: rebuildable projection and FTS surface.

CLI and migration report contracts are versioned separately under [`../interfaces/`](../interfaces/README.md).

Phase 5 adds optional version-1 review and promotion evidence to AI Artifact frontmatter. New
review/promotion operations require this evidence; legacy v2 objects remain readable. Exact fields
live in objects.schema.json. Old strict parsers may reject the extension; package downgrade never
rewrites it. The compatibility decision is in
[ADR-0018](../../plan/decisions/0018-phase5-local-revision-bound-ai-review.md).
