# ADR-0002: Separate record status from workflow stage

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

The initial design overloaded `status` with two meanings: whether an object is active/archived/superseded, and where a Source is in the capture-to-integration workflow. This creates invalid combinations, unclear filters, and difficult migrations. Note maturity and AI review state are additional independent dimensions.

## Decision

Use independent state dimensions:

- `record_status` describes object validity and applies to every object;
- `workflow_stage` describes Source processing progress;
- `maturity` describes Note maturity;
- `review_status` describes review state where applicable.

Source archival is represented by record status, not by workflow stage. The executable enum and applicability rules are authoritative in [`../../schemas/objects.schema.json`](../../schemas/objects.schema.json); semantics are explained in [`../data-model.md`](../data-model.md).

## Consequences

### Benefits

- Each field has one meaning and one lifecycle.
- Source workflow metrics no longer confuse archived or superseded records.
- Note maturity can evolve without changing record validity.
- Query filters and migrations become explicit.

### Costs and constraints

- Old `status` fields must be rejected or migrated rather than guessed.
- UI and projection tables need separate fields and filters.
- Cross-field validation must enforce which dimensions apply to each object kind.

## Alternatives considered

- One large per-kind `status` enum: rejected because shared operations would still require kind-specific interpretation.
- Encode all dimensions as tags: rejected because tags are not a controlled lifecycle contract.
- Keep archived in Source workflow: rejected because archival and processing progress are independent.

## Revisit when

New lifecycle dimensions require a separate decision. Existing fields should not absorb another meaning merely to avoid adding a field.
