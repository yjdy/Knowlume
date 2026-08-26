# Knowlume working rules

## Source of truth

- Markdown/YAML files are the durable source of truth.
- SQLite, caches, derived files, and public staging are disposable projections.
- Never write machine-specific absolute paths into tracked knowledge objects.

## Object boundaries

- Every object uses `schema_version: 1` and a stable prefixed ULID.
- Use `record_status` for object validity. Source processing uses `workflow_stage`.
- Notes use `maturity`; AI artifacts use `review_status`.
- Facts require a source ID and a source-type-specific locator.
- The first version has no Claim object. Relations target an object or a stable `section_id`.

## AI and publishing

- AI output starts as a private, unreviewed `ai_artifact`.
- AI output must not silently enter facts, default search/context, or public staging.
- Publishing is allowlist-based and must reject public-to-private dependencies.

## Change discipline

- Preserve stable IDs across file and heading renames.
- Treat schema changes as migrations; update schemas, templates, fixtures, and tests together.
- Do not implement production parser or domain code until Phase 0 contract tests pass.
