# Knowlume executable contracts

Machine-enforced fields and constraints are versioned. Contract v2 is the production target; Contract v1 is retained only for validation and migration.

| Area | Active contract | Historical contract |
|---|---|---|
| Objects and frontmatter | [`v2/objects.schema.json`](v2/objects.schema.json) | [`v1/objects.schema.json`](v1/objects.schema.json) |
| Note bodies | [`v2/note-body.schema.json`](v2/note-body.schema.json) | Fixed-section syntax in v1 fixtures |
| Source locators | [`v2/locator.schema.json`](v2/locator.schema.json) | [`v1/locator.schema.json`](v1/locator.schema.json) |
| Relation shards | [`v2/relations.schema.json`](v2/relations.schema.json) | [`v1/relations.schema.json`](v1/relations.schema.json) |
| SQLite projection | [`v2/sqlite-projection-v2.sql`](v2/sqlite-projection-v2.sql) | [`v1/sqlite-projection-v1.sql`](v1/sqlite-projection-v1.sql) |
| Machine interfaces and reports | [`interfaces/`](interfaces/README.md) | Not defined in v1 |
| Portable vault configuration | [`config/v1/`](config/README.md) | Not defined before Phase 1 |
| Machine-local lock and transaction state | [`state/v1/`](state/README.md) | Not defined before Phase 1 |

Active object creation templates live under [`../templates/v2/`](../templates/v2/README.md), and the
portable vault configuration template lives under
[`../templates/config/v1/`](../templates/config/v1/README.md). Maintained examples and rejected cases
live under [`../tests/fixtures/`](../tests/fixtures/). The migration policy is
[`../plan/migrations/v1-to-v2.md`](../plan/migrations/v1-to-v2.md).

Backward-incompatible durable changes require a new contract version, migration impact, templates, positive and negative fixtures, and executable acceptance tests.
