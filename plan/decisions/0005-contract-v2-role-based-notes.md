# ADR-0005: Contract v2 uses role-based Note sections

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

Contract v1 required four fixed sections and used `evergreen` as both a Note type and a maturity. It also allowed Note-level source and relation fields that could not bind provenance to one fact. Direct human writing without an external source was structurally possible but not a first-class workflow.

## Decision

Contract v2 defines Note types `idea`, `literature`, `concept`, and `synthesis`. `evergreen` is only a maturity. An Idea may be `seed` or `developing` and may evolve in place to Concept while preserving object and section IDs; the transition is recorded in `type_history`.

Note bodies use stable sections with explicit roles: `human`, `fact`, `ai`, and `evolution`. Every Note has at least one human section. Fact blocks carry adjacent Source and locator metadata. AI blocks carry an adjacent promoted Artifact reference. Facts and AI blocks are not durable relation targets.

The executable metadata contract lives under [`../../schemas/v2/`](../../schemas/v2/README.md). Maintained authoring examples live under [`../../templates/v2/`](../../templates/v2/README.md).

## Consequences

- Source-free human ideas are valid and may be public when rendered as opinion rather than fact.
- Fixed v1 section IDs are migration inputs, not v2 authoring rules.
- Parsers must validate body structure in addition to frontmatter.
- V1 Evergreen Notes and uncited fact blocks require human migration decisions.

## Alternatives considered

- Keep four empty sections in every Note: rejected because it makes direct writing cumbersome.
- Add first-class Claim objects: deferred by ADR-0004.
- Treat every uncited statement as a fact: rejected because it destroys the trust boundary.

