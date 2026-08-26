# Data model

> Status: Active  
> Baseline: contract version 1  
> Authoritative for: durable object semantics, identity, lifecycle, provenance, sections, and relations

The executable field contract is [`../schemas/objects.schema.json`](../schemas/objects.schema.json). Locator and relation shapes are defined by [`../schemas/locator.schema.json`](../schemas/locator.schema.json) and [`../schemas/relations.schema.json`](../schemas/relations.schema.json). This document explains semantics and must not redefine incompatible enums.

## Object types

| Kind | Responsibility |
|---|---|
| `source` | Stable source card and route back to original material |
| `note` | Human-maintained knowledge |
| `snippet` | Small, licensed extract from an OSS source fixed to a commit |
| `ai_artifact` | AI-produced material that has not been promoted into human knowledge |

Claim is not an object in v1.

## Identity and schema version

- Every object declares a contract version and a permanent typed ID. Exact field names, version values, prefixes, and patterns are defined only in [`objects.schema.json`](../schemas/objects.schema.json).
- File and heading renames never change object IDs.
- Duplicate IDs are contract errors and block strict lint and publishing.
- A schema change that cannot read existing files requires an explicit migration.

Creation examples are maintained in the [`templates/`](../templates/) directory. Valid object examples are the Markdown files under [`tests/fixtures/valid/`](../tests/fixtures/valid/); rejected contract shapes are under [`tests/fixtures/invalid/`](../tests/fixtures/invalid/).

## State dimensions

State dimensions are independent. Applicability, allowed values, and conditional requirements are defined by [`objects.schema.json`](../schemas/objects.schema.json).

| Field | Applies to | Meaning |
|---|---|---|
| object record state | every object | whether the durable record is current, archived, or replaced |
| source workflow state | Source only | progress from capture toward integration |
| note maturity | Note only | stability and reuse maturity of human knowledge |
| `review_status` | AI review surfaces | review state, never a substitute for object kind |

Archival is an object-record concern, not a Source workflow step. Integration means that a Source has contributed to concept or synthesis knowledge. The accepted rationale is recorded in [`decisions/0002-record-status-and-workflow-stage.md`](decisions/0002-record-status-and-workflow-stage.md).

## Note types

| `note_type` | Purpose |
|---|---|
| `literature` | Reading notes centered on one source |
| `concept` | Evolving understanding of one concept |
| `synthesis` | Conclusions synthesized across sources or notes |
| `evergreen` | Stable, reusable knowledge that may become publishable |

Current state lives in the current Markdown file. Ordinary history lives in Git; files are not copied into `note-v1.md`, `note-v2.md`, and similar manual versions.

## Stable sections and provenance

Human notes separate four surfaces using permanent section markers:

- original facts;
- human interpretation;
- AI inference;
- view evolution.

The canonical marker syntax is demonstrated by the four [`Note templates`](../templates/notes/) and the valid [`literature-note fixture`](../tests/fixtures/valid/literature-note.md). Marker validation and accepted IDs belong to the executable contracts and tests.

`section_id` survives heading and file renames. A fact binds a Source ID and a source-type-specific locator. Interpretations may lack a locator but must remain distinguishable from facts. AI inference remains explicitly marked even when embedded in a reviewed note.

Source-specific locator fields and preservation semantics are authoritative in [`sources-and-adapters.md`](sources-and-adapters.md); JSON validation is authoritative in the locator schema.

## Relations

The complete relation vocabulary, required fields, target ID formats, and optional locator shape are defined only in [`relations.schema.json`](../schemas/relations.schema.json). See the [`relation template`](../templates/relations.yaml), [`valid relation fixture`](../tests/fixtures/valid/relations.yaml), and invalid [`Claim`](../tests/fixtures/invalid/claim-relation.yaml) and [`missing-section`](../tests/fixtures/invalid/missing-section-relation.yaml) fixtures.

A relation points to an object using `to_id`, or to a stable section using `to_id + to_section_id`. V1 does not support Claim targets. Heading text and generated index segment IDs are not stable relation targets.

Markdown/Wikilinks provide navigation; typed relation blocks provide semantics; SQLite only stores their projection.

## Merge and supersede

- `summarizes` describes a note-to-source meaning; it is not a merge.
- `synthesizes` records conclusions derived across several sources or notes.
- Merge keeps source objects and marks them superseded instead of deleting them.
- Supersede means a new object replaces an old object without requiring body duplication.
- Search and publishing must surface or audit links to superseded objects.

## AI Artifact lifecycle

AI output begins as a private artifact:

```text
AI Artifact -> Human Review -> Accept or Reject -> Promote -> Note
```

Unpromoted artifacts are excluded from default search/context, fact sections, and public publishing. Promotion preserves the source artifact ID, reviewer, review time, model identity, and source references so that provenance is not lost.

Enforcement of AI and visibility boundaries is defined in [`security-publishing.md`](security-publishing.md).

## Contract evolution

Schema modifications follow this order:

1. record the decision and migration impact;
2. update JSON Schema;
3. update templates;
4. add valid and invalid fixtures;
5. update executable contract tests;
6. implement parser/domain changes;
7. provide a migration for existing files when required.
