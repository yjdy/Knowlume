# ADR-0004: Do not introduce Claim-level relations

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

The early relation vocabulary mentioned Claim targets, but the object model had no Claim identity, lifecycle, serialization, or migration contract. Introducing Claim as a first-class object would expand authoring, parsing, indexing, relation integrity, UI, and publishing scope before the file and section model is proven.

## Decision

The active contract does not define a Claim object or Claim-level relation. Typed relations point to complete objects or stable Note sections. Facts remain provenance-marked content inside stable sections rather than independently addressable entities.

The active relation semantics are defined in [`../data-model.md`](../data-model.md), and the executable contract rejects Claim IDs in [Contract v2 relations](../../schemas/v2/relations.schema.json).

## Consequences

### Benefits

- Phase 1 parser and domain scope remain bounded.
- Every relation target has an existing durable identity.
- Rebuild and referential-integrity tests stay understandable.
- User authoring does not require IDs on every sentence or bullet.

### Costs and constraints

- `supports` and `contradicts` cannot target one atomic claim inside a section.
- Relations may be coarser than the evidence they describe.
- A later Claim model will require migration from section-level relationships where finer granularity is desired.

## Alternatives considered

- First-class Claim objects: rejected due to scope and unresolved authoring semantics.
- Generated Claim IDs during indexing: rejected because rebuildable projections cannot own durable identity.
- Use line numbers inside notes: rejected because ordinary editing makes line numbers unstable.

## Revisit when

Consider a Claim ADR only after stable-section relations have real usage evidence showing that section-level granularity is insufficient. A future proposal must define durable Claim IDs, authoring syntax, migration, provenance, indexing, and publishing behavior together.
