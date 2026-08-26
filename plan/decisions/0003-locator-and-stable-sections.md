# ADR-0003: Use source-specific locators and stable section IDs

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

Traceability requires more than a Source ID. Papers, web pages, books, and repositories use different location systems, while URLs, headings, branches, and generated index segment IDs can change. Relations also need targets finer than a whole Note without becoming dependent on mutable heading text.

## Decision

Each source type has a versioned, machine-validatable locator schema. Mutable sources bind locators to an immutable version, capture time, or content hash. OSS locators require a fixed commit.

Note sections that can be referenced by relations receive permanent `section_id` markers. Object-level relations use an object ID; section-level relations use the object ID plus stable section ID. Titles, filenames, heading text, and generated segment IDs are not durable relation identities.

The executable locator contract is [`../../schemas/locator.schema.json`](../../schemas/locator.schema.json), and relation shape is [`../../schemas/relations.schema.json`](../../schemas/relations.schema.json). Source-specific semantics live in [`../sources-and-adapters.md`](../sources-and-adapters.md).

## Consequences

### Benefits

- Facts can return to a precise source location or immutable snapshot.
- Heading and file renames do not break typed relations.
- Locators can be linted, indexed, and rendered consistently.
- Future adapters can translate the same domain locator into native open actions.

### Costs and constraints

- Locator schemas differ by source type and require migrations when extended incompatibly.
- Stable section markers add visible structure to Markdown authoring.
- Partial locators require explicit warning behavior rather than silent acceptance.
- Web capture and attachment hashing add operational work.

## Alternatives considered

- Free-text locators: rejected because they cannot be reliably validated or transformed.
- Heading text as section identity: rejected because headings are routinely edited or localized.
- SQLite segment IDs as relation targets: rejected because the index is rebuildable and segment IDs may change.

## Revisit when

Revisit locator fields when real source fixtures reveal missing location semantics. Preserve versioned compatibility and stable IDs during extension.
