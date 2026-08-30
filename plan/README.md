# Knowlume design and implementation plans

`plan/` contains the active architecture, semantics, accepted decisions, migration policy, and delivery gates. Executable schemas and tests remain authoritative for machine-enforced fields.

## Current baseline

Phase 0R, Phase 1, Phase 2A, and Phase 2B are complete. Phase 2B passed local, distribution,
isolated-install, and Windows/macOS/Linux Python 3.13–3.14
[CI](https://github.com/yjdy/Knowlume/actions/runs/33252123661) and
[package smoke](https://github.com/yjdy/Knowlume/actions/runs/33252123610) gates. Earlier Phase 2A and
Phase 1 evidence remains linked from the [roadmap](roadmap.md). Phase 3 projection, bilingual search,
and scoped context behavior is implemented under ADR-0016 and has passed local, distribution, and
isolated-wheel gates; required cross-platform remote gates remain pending.

The cross-platform Python package and release-engineering foundation is implemented independently
of the feature phases. Public command status and verification evidence are tracked in
[`CLI.md`](../CLI.md).

## Active documents

| Document | Authority |
|---|---|
| [`architecture.md`](architecture.md) | system boundaries, layers, vault topology |
| [`data-model.md`](data-model.md) | objects, role-based Note bodies, identity, lifecycle, relations |
| [`sources-and-adapters.md`](sources-and-adapters.md) | source preservation, locators, external adapters |
| [`storage-index-search.md`](storage-index-search.md) | durable storage, projection, indexing, search |
| [`interfaces.md`](interfaces.md) | CLI, JSON, workflows, Web |
| [`security-publishing.md`](security-publishing.md) | trust boundaries, AI, visibility, publishing |
| [`roadmap.md`](roadmap.md) | phases, command ownership, delivery gates |
| [`distribution.md`](distribution.md) | Python packaging, runtime assets, compatibility, release trust |
| [`phase1-goal.md`](phase1-goal.md) | Phase 1 execution goal, milestones, acceptance checks, and Git rollback boundaries |
| [`phase2a-goal.md`](phase2a-goal.md) | Phase 2A Paper/Zotero execution goal, milestones, acceptance checks, and Git rollback boundaries |
| [`phase2b-goal.md`](phase2b-goal.md) | Phase 2B unified Source capture goal, project-level OSS boundary, milestones, and acceptance checks |
| [`phase3-goal.md`](phase3-goal.md) | Phase 3 projection, bilingual search, scoped context, milestones, and release-readiness gates |
| [`migrations/v1-to-v2.md`](migrations/v1-to-v2.md) | v1-to-v2 migration behavior |
| [`decisions/`](decisions/) | accepted architecture decisions |
| [`chapter-map.md`](chapter-map.md) | completed historical design migration audit |

The frozen original design is retained at [`archive/design-baseline-v0.1.md`](archive/design-baseline-v0.1.md) and is not an active specification.
