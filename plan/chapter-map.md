# DESIGN_PLAN.md migration completion map

The original design was audited and split into active thematic documents. The frozen byte-for-byte baseline remains under [`archive/`](archive/design-baseline-v0.1.md); the root working copy has been retired.

| Original area | Active authority | Status |
|---|---|---|
| Positioning, principles, architecture, layout | [`architecture.md`](architecture.md) | Complete |
| Objects, state, sections, relations, evolution | [`data-model.md`](data-model.md) | Complete |
| Source preservation and adapters | [`sources-and-adapters.md`](sources-and-adapters.md) | Complete |
| SQLite, Git, indexing, search, context | [`storage-index-search.md`](storage-index-search.md) | Complete |
| CLI, JSON, workflows, Web | [`interfaces.md`](interfaces.md) | Complete |
| Security, AI, privacy, publishing | [`security-publishing.md`](security-publishing.md) | Complete |
| Phases, scope, commands, acceptance | [`roadmap.md`](roadmap.md) | Complete |
| Contract v1 migration | [`migrations/v1-to-v2.md`](migrations/v1-to-v2.md) | Complete |
| Post-baseline package distribution | [`distribution.md`](distribution.md) | Complete |
| Post-baseline vault configuration and transaction protocol | [`decisions/0011-phase1-vault-and-transaction-contracts.md`](decisions/0011-phase1-vault-and-transaction-contracts.md), [`schemas/config/`](../schemas/config/README.md), [`schemas/state/`](../schemas/state/README.md) | Complete |

## Completion checks

- [x] Each topic has one active authority.
- [x] README and AGENTS contain only entry-point and operational summaries.
- [x] Machine fields and enums are owned by versioned schemas.
- [x] Internal documentation links are executable acceptance checks.
- [x] Contract v1 is frozen under versioned historical directories.
- [x] Contract v2 schemas, templates, fixtures, projection, and tests exist.
- [x] The root `DESIGN_PLAN.md` working copy is retired; the archive remains.
