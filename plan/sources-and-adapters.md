# Sources and adapters

> Status: Active  
> Baseline: v0.1  
> Authoritative for: source preservation, source-specific locators, and external software boundaries

Source cards are durable metadata and access routes, not copies of full source content. Their executable field contract is [`../schemas/objects.schema.json`](../schemas/objects.schema.json); locator validation is [`../schemas/locator.schema.json`](../schemas/locator.schema.json).

Use the [`Source template`](../templates/source-card.md) for creation. Maintained examples are the valid [`paper`](../tests/fixtures/valid/paper-source.md), [`web`](../tests/fixtures/valid/web-source.md), [`book`](../tests/fixtures/valid/book-source.md), and [`OSS`](../tests/fixtures/valid/oss-source.md) fixtures.

## Common source rules

- A Source has a stable ID, canonical identity, capture metadata, visibility, record status, and workflow stage.
- Machine-specific absolute paths are forbidden in tracked source cards.
- External attachments are resolved through adapter identifiers.
- Canonicalization and duplicate detection occur before creating a source card.
- Source material that can change must preserve a capture time, immutable version, or content hash.

## Paper

Zotero normally stores metadata and PDF attachments. Knowlume stores the source card, canonical URL or DOI, Zotero library/item/attachment identifiers, tags, and reading state.

Paper facts should prefer a location visible to a human reader rather than an internal PDF byte offset. Exact locator fields and requirements belong to [`locator.schema.json`](../schemas/locator.schema.json); a valid locator is exercised in the [`relation fixture`](../tests/fixtures/valid/relations.yaml).

## Web

Web source cards preserve the canonical URL and capture time. A Zotero snapshot or PDF is preferred when the cited page may change.

Web locators must bind the cited position to a captured or immutable representation; a live URL alone is insufficient. The exact alternatives are defined in the locator schema. [`web-locator-missing-snapshot.yaml`](../tests/fixtures/invalid/web-locator-missing-snapshot.yaml) demonstrates a rejected locator.

## Book

Books are identified through ISBN, DOI, Zotero key, or another stable bibliographic reference. PDF/EPUB files remain in the reference manager by default; Knowlume stores source cards and linked notes.

Book locators must distinguish editions whenever pagination differs. Exact identity and position fields are defined in the locator schema.

## Open-source project

Knowlume does not retain complete repositories as durable knowledge. The OSS Source and Snippet fields are defined in [`objects.schema.json`](../schemas/objects.schema.json), with maintained examples in the [`OSS Source`](../tests/fixtures/valid/oss-source.md) and [`Snippet`](../tests/fixtures/valid/snippet.md) fixtures.

Temporary reading uses shallow/partial clone or sparse checkout under `.cache/repos/`. Important code may be retained as a Snippet when it satisfies the executable provenance contract.

An OSS locator is invalid without an immutable commit. Branch names may be displayed but cannot replace the commit.

## Attachment durability

A single external item key is not a backup. Where an attachment is important, the Source retains the recovery identifiers and optional integrity evidence required by the object schema.

Backup and recovery must cover both:

1. the tracked Knowlume repository;
2. Zotero data and attachment storage.

Knowlume must report an unavailable attachment without rewriting its stable source identity.

## Adapter contracts

### Zotero

- Use a supported Zotero Local API or local service; never read `zotero.sqlite` directly.
- Resolve item metadata and attachments from library/item keys.
- Map external metadata into domain values without leaking Zotero schema into domain code.
- `source open` returns an openable attachment result or a typed unavailable error.

### Obsidian

- Obsidian is a human Markdown editor, not a database.
- Ordinary Markdown links and Wikilinks are navigation surfaces.
- Object and section IDs carry identity; filenames and headings carry readability.
- Core behavior must not depend on `.obsidian` private state.

### Git

Git adapter behavior is defined with storage history in [`storage-index-search.md`](storage-index-search.md). The adapter exposes status, diff, history, and changed-file information through a port.

### Quartz

Quartz consumes only audited `public-staging`. It never receives the private knowledge tree as its input. Publishing rules are defined in [`security-publishing.md`](security-publishing.md).

### Future native components

Future editors, reference managers, or publishers implement stable ports such as `SourceStore`, `NoteStore`, `ReferenceManager`, `SearchBackend`, and `Publisher`. Replacing an adapter must not require a durable data-model migration.

## Legal boundary

Automated checks report license, copyright, redistribution, and attribution evidence and risks. They do not provide legal advice. Uncertain publication or excerpt rights require human review.
