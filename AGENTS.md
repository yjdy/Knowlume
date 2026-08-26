# Knowlume working rules

These rules apply to the entire repository. They are operational constraints for human contributors and automated agents, not a roadmap or architecture narrative.

## Authority and documentation

Use this order when sources disagree:

1. `schemas/` and executable contract tests define machine-enforced fields and constraints.
2. This file defines repository working and safety rules.
3. Active documents under `plan/` define semantics, architecture, and accepted decisions.
4. `README.md` is an entry point and summary.
5. `plan/archive/` is historical evidence and is not an active specification.

Do not duplicate an authoritative field table or rule in another document. Link to its owner instead. Update [`plan/chapter-map.md`](plan/chapter-map.md) when documentation ownership changes.

## Durable and generated data

- Treat tracked Markdown/YAML, schemas, templates, migrations, tests, configuration, and source code as durable.
- Treat SQLite projections, caches, derived output, temporary clones, logs, virtual environments, and public staging as disposable.
- Never make disposable state the only source of a business fact.
- Never place machine-specific absolute paths, credentials, tokens, or private attachment contents in tracked objects, fixtures, logs, or examples.
- Do not commit large PDF/EPUB files, Zotero storage, temporary repositories, or generated public output unless an explicit reviewed policy changes this boundary.

## Change workflow

Before editing, read the active design document and accepted ADR that own the behavior. Keep changes scoped to the requested feature and preserve unrelated user work.

For durable-contract changes, use this order:

1. record or update the decision and migration impact;
2. update JSON Schema;
3. update templates;
4. add or update valid and invalid fixtures;
5. update executable acceptance tests;
6. change production parser/domain/application code;
7. provide a migration when existing files are not directly readable.

Do not change a schema, parser, template, or domain model in isolation. Backward-incompatible machine output or durable-file changes require an explicit contract/version decision.

## Knowledge integrity

- Preserve object IDs across file renames, heading changes, merges, and supersession.
- Preserve stable `section_id` values when editing section titles or moving sections.
- Use the state dimensions defined by the object schema; do not reintroduce an overloaded `status` field.
- Facts require a valid Source ID and source-type-specific locator.
- Relations target existing objects or stable sections. Do not invent generated or line-number-based durable identities.
- Never silently delete an object to represent merge or supersession.
- File writes must be atomic and conflict-aware; do not overwrite content changed by another process since it was read.

Detailed semantics are owned by [`plan/data-model.md`](plan/data-model.md) and [`plan/sources-and-adapters.md`](plan/sources-and-adapters.md).

## AI and trust boundaries

- AI-produced content begins as a private, reviewable AI Artifact.
- Do not silently move AI content into facts, ordinary retrieval, trusted human notes, or public output.
- Promotion requires an explicit human-review action and preserved provenance.
- Do not send private objects or attachment content to an external model without an explicit caller scope and release policy.
- Public-safe operations fail closed on private, unresolved, superseded, or unreviewed dependencies.

Publishing must start from an explicit allowlist, audit the complete dependency closure, and build an isolated staging tree. Never give the complete private knowledge tree to a publisher and rely on downstream filtering. Follow [`plan/security-publishing.md`](plan/security-publishing.md).

## External systems

- Access Zotero through a supported API; never read or modify its private SQLite schema directly.
- Treat Obsidian as a Markdown editor, not as the domain database.
- Give Quartz only audited public staging.
- Keep adapter-specific types and schemas outside the domain layer.
- Use immutable commits for OSS provenance; a branch name alone is not a stable source locator.

## Verification

Run the smallest relevant checks while working, then run the full repository-defined test suite before handing off a contract or production change.

Repository verification command:

```powershell
uv run --no-sync pytest -p no:cacheprovider
```

Also validate internal documentation links when changing README, AGENTS, or `plan/`. Do not claim a command, compatibility target, or feature is working unless it was executed or supported by repository evidence.

## Git hygiene

- Do not stage, commit, push, rewrite history, or delete branches unless explicitly requested.
- Keep generated, private, and environment-specific files ignored.
- Inspect staged changes before committing and use a message that describes the user-visible outcome.
- Never bypass failing contract, security, or publish checks to produce a commit or artifact.
