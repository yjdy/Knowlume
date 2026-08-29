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

Paper sources support DOI, arXiv, Zotero, and ordinary bibliographic metadata. Facts cite a
human-verifiable page, section, figure, table, or equivalent locator. A Source ID is the durable
domain identity. DOI and arXiv are canonical external identifiers; Zotero identifiers are recovery
routes.

Phase 2A automated capture requires DOI or arXiv after metadata resolution. Existing v2 Sources
with only a Zotero route remain readable, but the automated service does not create new ones. DOI
normalization removes labels and DOI URL prefixes, trims whitespace, and lowercases the result.
arXiv normalization accepts old and new identifier forms, removes labels and URL prefixes, and
separates an optional version. Duplicate identity uses the versionless arXiv ID.

DOI is preferred when both identifiers exist, while arXiv remains an alias. A match on either
identifier returns the existing Source. If the identifiers point to different Sources, capture or
synchronization fails rather than guessing or merging.

Phase 2A resolves only an exact stored Zotero reference in production; its internal capture service
receives metadata through an injected port. Phase 2B adds production personal-library candidate
search. For new unified capture, Paper accepts only top-level `journalArticle`, `conferencePaper`,
`preprint`, `thesis`, `report`, and `manuscript` items. Book accepts only top-level `book`.
`bookSection`, a missing type, and every other type are not guessed. Existing exact-reference Paper
Sources remain readable and synchronizable without retroactive item-type reclassification. These
boundaries are frozen by
[`ADR-0014`](decisions/0014-phase2a-acceptance-and-phase2b-zotero-classification.md).

## Web

A live URL and `captured_at` alone cannot support a durable fact. A web snapshot reference contains a provider, opaque identifier, capture time, and content hash; adapters interpret the provider-specific identifier. Public facts require both an eligible public Source and a recoverable snapshot reference.

Phase 2B freezes the first accepted snapshot for a canonical URL. Repeated capture returns the
existing Source without replacing snapshot identity or bytes. Web snapshot replacement and Web
`source sync` are deferred.

## Book

Books use ISBN, DOI, Zotero, or another stable bibliographic identity. Any locator that uses page numbers must also identify the edition or ISBN so pagination is unambiguous.

Phase 2B captures Book metadata but does not extend `source sync` beyond its Phase 2A Paper scope.

## Open-source software

An OSS source identifies the host, full repository path, and immutable commit. Repository paths may contain nested GitLab groups. Branch names are display metadata and never replace a commit.

Phase 2B accepts only credential-free HTTP(S) repository-root URLs. GitHub, GitLab, and configured
hosts are recognized automatically; `--type repo` can select another self-hosted Git server but
cannot bypass project-root or remote-HEAD validation. The adapter resolves the current default
remote HEAD through read-only Git reference discovery and stores the full commit. It rejects
query/fragment values, blob/tree/file/subdirectory routes, and arbitrary revision input. An
unchanged HEAD returns the existing Source; a changed HEAD is a different immutable Source identity.

The Phase 2B adapter does not clone, read repository files or blobs, analyze code, or inspect
license files. The existing required `license` field is `NOASSERTION`; no license-evidence field is
added. Full clones remain disposable-only state for any future feature and are not part of this
capture path.

An overall project note is the existing Literature Note linked to the OSS Source by `summarizes`.
Contract v2 Snippets and `snippet_from` relations remain readable, but Snippet creation is
indefinitely deferred and has no assigned phase. A future creation workflow requires a new accepted
ADR covering content recovery, path/range safety, license review, publication approval, and atomic
writes.

## Attachment durability

Recovery covers both the tracked Knowlume vault and external attachment storage such as Zotero. Important attachments should retain adapter identifiers and integrity evidence. Missing attachments produce a typed availability finding without rewriting the Source.

Phase 2A manages at most one primary PDF. Exactly one readable PDF records its Zotero recovery route,
filename, media type, size, adapter version, and SHA-256. No candidate produces an availability
warning and does not block bibliographic Source creation. Multiple candidates produce an ambiguity
warning and no primary attachment is guessed. Supplementary and multi-attachment selection is
deferred.

An attachment path and attachment body remain disposable and must not enter the Vault. A stored hash
that no longer matches the recovered bytes is a provenance conflict: ordinary synchronization and
open operations do not silently accept replacement material or rewrite Fact locators.

## Adapter boundaries

### Zotero

- Phase 2A uses the supported loopback Local API, requests API version 3, and performs read
  operations only. It never accesses `zotero.sqlite` directly.
- Production configuration cannot redirect the Phase 2A adapter to a non-loopback endpoint. Cloud
  Web API access, OAuth, and Zotero mutation are deferred.
- Resolve metadata and a primary attachment from library/item identifiers. Use disposable cache for
  recovered bytes and verify stored integrity before opening them through the operating system.
- Translate adapter data into domain values without leaking Zotero internals into the domain layer.
- Missing optional dependencies, disabled API, timeout, permission failure, missing items, and
  malformed responses produce typed capability or availability failures rather than partial writes.
- Phase 2B quick search is only a candidate reducer: enumerate all pages, re-normalize returned
  identifiers, apply exact matching, and then enforce the accepted Paper/Book item-type boundary.

### Zotero synchronization ownership

Human-owned Source fields are visibility, record status, workflow stage, tags, and body content.
Zotero manages bibliographic title, authors, year, DOI, arXiv, canonical URL, and primary-attachment
metadata. The application manages the Source ID, update time, Zotero item version, synchronization
time, and a deterministic hash of the normalized Zotero-managed fields.

The synchronization baseline is durable in the Source card. A managed-field hash mismatch detects
local edits before fetching remote changes. Identity removal or replacement, identifier collision,
changed attachment bytes, or a concurrent file checksum change stops synchronization. Human-owned
fields are never overwritten.

When no conflict exists, synchronization updates adapter-owned fields atomically. A no-op is
successful and byte-preserving. An old Source without a baseline adopts one automatically only when
its current managed values already equal normalized Zotero metadata; otherwise explicit remote
adoption is required. Replacing a known attachment hash also requires a separate explicit action and
reports that Fact locators need review.

### Obsidian

Obsidian is a Markdown editor. Stable object and section IDs carry identity; filenames, headings, links, and Wikilinks are presentation and navigation surfaces. Core behavior cannot depend on private `.obsidian` state.

### Git and Quartz

Git history behavior is defined in [storage, index, and search](storage-index-search.md). Quartz receives only the audited staging tree described in [security and publishing](security-publishing.md), never the private vault.

## Legal boundary

Automated checks collect license, copyright, redistribution, and attribution evidence. They do not provide legal advice; uncertain rights require human review.

Phase 2B project-level OSS capture performs no automated license-file inspection and records
`NOASSERTION`; publication therefore remains fail-closed until rights are resolved by a future
reviewed workflow.
