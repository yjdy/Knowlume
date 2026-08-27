# Knowlume design and implementation plans

`plan/` contains the active architecture, semantics, accepted decisions, migration policy, and delivery gates. Executable schemas and tests remain authoritative for machine-enforced fields.

## Current baseline

Phase 0R is complete. Phase 1 production implementation has passed local and distribution gates;
the final cross-platform CI evidence is pending before the phase status can change to Complete.

The cross-platform Python package and release-engineering foundation is implemented independently of the feature phases. It exposes only verified release diagnostics until Phase 1 commands satisfy their gates.

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
| [`migrations/v1-to-v2.md`](migrations/v1-to-v2.md) | v1-to-v2 migration behavior |
| [`decisions/`](decisions/) | accepted architecture decisions |
| [`chapter-map.md`](chapter-map.md) | completed historical design migration audit |

The frozen original design is retained at [`archive/design-baseline-v0.1.md`](archive/design-baseline-v0.1.md) and is not an active specification.
