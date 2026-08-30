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
| Phase 1 Vault configuration and transaction protocol | [`decisions/0011-phase1-vault-and-transaction-contracts.md`](decisions/0011-phase1-vault-and-transaction-contracts.md) | Complete |
| Phase 2A Paper identity, Zotero, attachment, synchronization, workflow design, and acceptance clarification | [`phase2a-goal.md`](phase2a-goal.md), [`ADR-0012`](decisions/0012-phase2a-paper-zotero-design.md), [`ADR-0014`](decisions/0014-phase2a-acceptance-and-phase2b-zotero-classification.md) | Design ownership recorded |
| Phase 2B unified Source capture, Zotero classification, provenance coherence, anonymous Git resolution, project-level OSS boundary, Literature Note reuse, and deferred Snippet creation | [`phase2b-goal.md`](phase2b-goal.md), [`ADR-0013`](decisions/0013-phase2b-project-level-oss-and-deferred-snippets.md), [`ADR-0014`](decisions/0014-phase2a-acceptance-and-phase2b-zotero-classification.md), [`ADR-0015`](decisions/0015-phase2b-provenance-and-anonymous-git.md) | Design ownership recorded |
| Phase 3 state-directory SQLite, deterministic projection/segments, bilingual tokenizer, filtered search, scoped context, and release readiness | [`phase3-goal.md`](phase3-goal.md), [`ADR-0016`](decisions/0016-phase3-deterministic-projection-search-context.md) | Design and implementation ownership recorded; remote gates pending |

## Completion checks

- [x] Each topic has one active authority.
- [x] README and AGENTS contain only entry-point and operational summaries.
- [x] Machine fields and enums are owned by versioned schemas.
- [x] Internal documentation links are executable acceptance checks.
- [x] Contract v1 is frozen under versioned historical directories.
- [x] Contract v2 schemas, templates, fixtures, projection, and tests exist.
- [x] The root `DESIGN_PLAN.md` working copy is retired; the archive remains.
