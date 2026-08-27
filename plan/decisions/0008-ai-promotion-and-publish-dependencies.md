# ADR-0008: AI promotion preserves a private audit edge

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

Human-reviewed AI assistance must remain traceable without requiring private prompts or Artifact bodies to become public. Treating every relation as a publish dependency would make reviewed AI-assisted Notes impossible to publish.

## Decision

AI output starts as a private Artifact. Only a promoted Artifact may contribute an AI block to a Note. Promotion records model, reviewer, review time, input references, resulting Note, and a `promoted_from` relation.

Publishing classifies edges as content dependencies, navigation relationships, or internal audit relationships. Content dependencies must be public and enter the closure. Navigation targets render only when public. Internal promotion audit edges remain private; the public manifest may retain disclosure metadata and hashes but never the Artifact body.

## Consequences

- Reviewed AI-assisted Notes may be public.
- Public Facts still require public Sources and valid locators.
- Unreviewed or accepted-but-unpromoted AI never enters ordinary Notes, default retrieval, or public staging.

## Alternatives considered

- Publish the Artifact with the Note: rejected because it exposes private prompts and intermediate content.
- Forbid all AI-assisted publication: rejected because it discards the value of explicit human review.

