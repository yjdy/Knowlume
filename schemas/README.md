# Knowlume schema contracts

Phase 0 freezes contract version `1` in three executable JSON Schemas:

- `objects.schema.json`: Source, Note, Snippet, and AI Artifact frontmatter.
- `locator.schema.json`: paper, web, book, and OSS source locators.
- `relations.schema.json`: typed relations targeting objects or stable sections.

All schemas use JSON Schema Draft 2020-12. Markdown fixtures are validated by extracting YAML frontmatter. Schema changes require a versioned migration and matching updates to templates, fixtures, and acceptance tests.
