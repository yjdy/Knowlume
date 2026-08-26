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

- Every object has `schema_version: 1`.
- IDs are permanent prefixed ULIDs: `src_`, `note_`, `snip_`, or `ai_` plus a 26-character Crockford ULID.
- File and heading renames never change object IDs.
- Duplicate IDs are contract errors and block strict lint and publishing.
- A schema change that cannot read existing files requires an explicit migration.

## State dimensions

State dimensions are independent:

| Field | Applies to | Meaning |
|---|---|---|
| `record_status` | every object | `active`, `archived`, or `superseded` |
| `workflow_stage` | Source only | `inbox`, `reading`, `processed`, or `integrated` |
| `maturity` | Note only | `seed`, `developing`, `mature`, or `evergreen` |
| `review_status` | AI review surfaces | review state, never a substitute for object kind |

Source archival is `record_status: archived`; `archived` is not a workflow stage. `integrated` means that a source has contributed to concept or synthesis knowledge.

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

```markdown
<!-- section_id: sec_original_facts -->
## 原文事实

<!-- section_id: sec_my_interpretation -->
## 我的理解

<!-- section_id: sec_ai_inference -->
## AI 推论

<!-- section_id: sec_view_evolution -->
## 观点演化
```

`section_id` survives heading and file renames. A fact binds a Source ID and a source-type-specific locator. Interpretations may lack a locator but must remain distinguishable from facts. AI inference remains explicitly marked even when embedded in a reviewed note.

Source-specific locator fields and preservation semantics are authoritative in [`sources-and-adapters.md`](sources-and-adapters.md); JSON validation is authoritative in the locator schema.

## Relations

V1 relation types are:

```text
cites, derived_from, summarizes, synthesizes,
supports, contradicts, related_to, snippet_from, supersedes
```

A relation points to an object using `to_id`, or to a stable section using `to_id + to_section_id`. V1 does not support Claim targets. Heading text and generated index segment IDs are not stable relation targets.

Relations may include a source locator, reason, and creator. Markdown/Wikilinks provide navigation; typed relation blocks provide semantics; SQLite only stores their projection.

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
