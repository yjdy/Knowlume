# Sources and adapters

> Status: Active — Contract v2
> Authoritative for: source preservation, source-specific locators, and external-system boundaries

Source cards retain durable identity, metadata, and recovery references; they do not duplicate complete source content. Executable fields are defined by the [v2 object schema](../schemas/v2/objects.schema.json), and precise positions by the [v2 locator schema](../schemas/v2/locator.schema.json). New content uses the [v2 source template](../templates/v2/source-card.md).

## Common rules

- Source IDs remain stable when metadata or access routes change.
- Tracked cards contain no machine-specific absolute paths, credentials, or private attachment bodies.
- Canonicalization and duplicate detection happen before creation.
- Mutable material requires a recoverable snapshot or immutable version plus integrity evidence.
- Adapter identifiers may locate external attachments, but an unavailable adapter never changes source identity.

## Paper

Paper sources support DOI, arXiv, Zotero, and ordinary bibliographic identity. Facts cite a human-verifiable page, section, figure, table, or equivalent locator. Zotero identifiers are recovery routes, not domain identity.

## Web

A live URL and `captured_at` alone cannot support a durable fact. A web snapshot reference contains a provider, opaque identifier, capture time, and content hash; adapters interpret the provider-specific identifier. Public facts require both an eligible public Source and a recoverable snapshot reference.

## Book

Books use ISBN, DOI, Zotero, or another stable bibliographic identity. Any locator that uses page numbers must also identify the edition or ISBN so pagination is unambiguous.

## Open-source software

An OSS source identifies the host, full repository path, and immutable commit. Repository paths may contain nested GitLab groups. Branch names are display metadata and never replace a commit.

Temporary clones belong in disposable cache storage. Durable excerpts are Snippets with a Source, immutable commit, relative path, valid inclusive line range, license evidence, and explicit publication approval.

## Attachment durability

Recovery covers both the tracked Knowlume vault and external attachment storage such as Zotero. Important attachments should retain adapter identifiers and integrity evidence. Missing attachments produce a typed availability finding without rewriting the Source.

## Adapter boundaries

### Zotero

- Use a supported API or local service; never access `zotero.sqlite` directly.
- Resolve metadata and attachments from library/item identifiers.
- Translate adapter data into domain values without leaking Zotero internals into the domain layer.

### Obsidian

Obsidian is a Markdown editor. Stable object and section IDs carry identity; filenames, headings, links, and Wikilinks are presentation and navigation surfaces. Core behavior cannot depend on private `.obsidian` state.

### Git and Quartz

Git history behavior is defined in [storage, index, and search](storage-index-search.md). Quartz receives only the audited staging tree described in [security and publishing](security-publishing.md), never the private vault.

## Legal boundary

Automated checks collect license, copyright, redistribution, and attribution evidence. They do not provide legal advice; uncertain rights require human review.
