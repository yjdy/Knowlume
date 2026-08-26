# Knowlume schema contracts

Phase 0 freezes contract version `1` in three executable JSON Schemas and one executable SQLite projection:

- `objects.schema.json`: Source, Note, Snippet, and AI Artifact frontmatter.
- `locator.schema.json`: paper, web, book, and OSS source locators.
- `relations.schema.json`: typed relations targeting objects or stable sections.
- [`sqlite-projection-v1.sql`](sqlite-projection-v1.sql): rebuildable tables, keys, indexes, metadata, and FTS5 surface.

The JSON Schemas use Draft 2020-12. Markdown fixtures are validated by extracting YAML frontmatter. The SQL contract is executable against SQLite with FTS5 enabled. Contract changes require a versioned migration and matching updates to templates, fixtures, and acceptance tests.

## Templates and executable examples

| Contract | Creation template | Valid examples | Invalid examples |
|---|---|---|---|
| Source object | [`source-card.md`](../templates/source-card.md) | [`paper`](../tests/fixtures/valid/paper-source.md), [`web`](../tests/fixtures/valid/web-source.md), [`book`](../tests/fixtures/valid/book-source.md), [`OSS`](../tests/fixtures/valid/oss-source.md) | [`overloaded status`](../tests/fixtures/invalid/overloaded-status-source.md) |
| Note object and stable sections | [`templates/notes/`](../templates/notes/) | [`literature note`](../tests/fixtures/valid/literature-note.md), [`public note`](../tests/fixtures/valid/public-note.md) | Referencing failures are covered by relation fixtures |
| Snippet object | [`snippet.md`](../templates/snippet.md) | [`snippet fixture`](../tests/fixtures/valid/snippet.md) | Contract failures belong under `tests/fixtures/invalid/` |
| AI Artifact | [`ai-artifact.md`](../templates/ai-artifact.md) | [`AI fixture`](../tests/fixtures/valid/ai-artifact.md) | Visibility/review failures belong under `tests/fixtures/invalid/` |
| Relation | [`relations.yaml`](../templates/relations.yaml) | [`relations fixture`](../tests/fixtures/valid/relations.yaml) | [`Claim target`](../tests/fixtures/invalid/claim-relation.yaml), [`missing section`](../tests/fixtures/invalid/missing-section-relation.yaml), [`public-to-private`](../tests/fixtures/invalid/public-private-relation.yaml) |
| Locator | Embedded by the relation template | Paper locator in the valid relation fixture | [`web locator without snapshot identity`](../tests/fixtures/invalid/web-locator-missing-snapshot.yaml) |

These linked files are the maintained examples. Design documents should link here instead of embedding field-complete YAML or JSON copies.
