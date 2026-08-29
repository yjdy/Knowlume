# ADR-0012: Freeze Phase 2A Paper and Zotero behavior

- Status: Accepted
- Date: 2026-08-28
- Decision owners: Knowlume maintainers

> Completion boundary clarification: [`ADR-0014`](0014-phase2a-acceptance-and-phase2b-zotero-classification.md)
> records that production DOI/arXiv candidate search and Zotero Paper/Book item-type classification
> belong to Phase 2B. Existing exact-reference Phase 2A behavior remains compatible.

## Context

Phase 2A is the first Source-capture slice. Existing Contract v2 permits Paper recovery through a
canonical URL, DOI, or Zotero key, while the active source design says Zotero identifiers are
recovery routes rather than domain identity. The roadmap also requires DOI/arXiv canonicalization,
Zotero attachment recovery, idempotency, and Source workflow commands without exposing the
Phase 2B unified `kb add` command.

The design must distinguish three things that were previously conflated: a valid existing Source
file, eligibility for deterministic automated capture, and an adapter route that can recover
external material. It must also prevent metadata synchronization or changed PDF bytes from silently
invalidating human edits and Fact locators.

## Decision

### Identity and Contract compatibility

A Knowlume Source ID is the permanent domain identity. DOI and arXiv values are canonical external
identifiers used for recognition and duplicate detection. Zotero library, item, and attachment keys
are adapter recovery routes and never replace the Source ID.

Phase 2A automated Paper capture requires a DOI or arXiv ID after metadata resolution. A Zotero item
without either identifier is ineligible, produces a typed finding, and writes nothing. Existing
Contract v2 Sources that rely only on a Zotero route remain readable; schema validity is not the same
as Phase 2A automated-capture eligibility.

DOI normalization removes a `doi:` label or DOI URL prefix, trims surrounding whitespace, validates
the DOI shape without imposing a publisher-specific suffix grammar, and lowercases the result.
arXiv normalization removes an `arXiv:` label or arXiv URL prefix, preserves either the old or new
identifier form, separates an optional `vN`, and uses the versionless base ID for duplicate
detection.

When both identifiers exist, DOI is the preferred canonical external identity and arXiv is an
alias. Matching either identifier returns the existing Source. If DOI and arXiv resolve to different
Sources, capture and synchronization fail with an identity conflict; the system does not auto-merge
or choose one.

Contract v2 receives additive, optional fields rather than a v3 migration. The future schema update
will cover arXiv identity/version, Zotero library type and item version, synchronization time and
managed-field hash, and primary-attachment version, filename, media type, size, and SHA-256.
Contract v1 remains byte-stable. Exact field spelling becomes machine authority only when the v2
schema, parser, template, fixtures, and tests change together.

### Zotero boundary and primary attachment

Phase 2A uses only Zotero's supported Local API on a loopback endpoint and requests API version 3.
The adapter is read-only, never opens `zotero.sqlite`, and rejects a production endpoint that is not
loopback. Cloud Web API access, OAuth, and Zotero mutations are deferred.

The first slice manages at most one primary PDF:

- one readable PDF records its adapter route plus filename, media type, size, version, and SHA-256;
- zero candidates preserves the Source and reports an availability warning;
- more than one candidate preserves the Source but records no guessed primary attachment and
  reports an ambiguity warning.

No absolute file path or attachment body is written to the Vault. `source open` resolves the
attachment through the adapter into disposable cache, verifies the stored hash when present, and
then delegates to the operating system. An unavailable attachment is an external-dependency
failure. A different hash is a provenance conflict and is not silently accepted.

### Synchronization ownership and conflicts

Human-owned fields are visibility, record status, workflow stage, tags, and Source body content.
Zotero-managed fields are bibliographic title, authors, year, DOI, arXiv, canonical URL, and primary
attachment metadata. The application owns the Source ID, update time, Zotero item version,
synchronization time, and managed-field hash.

The managed-field hash is calculated from canonical JSON of the normalized Zotero-managed fields,
using UTF-8, Unicode NFC, sorted keys, and omitted absent values. It is stored in the Source card so
conflict detection survives cache deletion and transfer to another computer.

`source sync` is automatic only when safe:

1. compare current managed fields with the stored baseline;
2. retrieve and normalize the current Zotero item;
3. reject local managed-field edits, identity removal/replacement, identifier collisions, and
   changed attachment bytes;
4. preserve every human-owned field;
5. atomically write only when durable content changes.

A no-op is successful and byte-preserving. A pre-existing Source without a baseline establishes one
automatically only when its managed fields already equal the normalized Zotero values. Otherwise an
explicit future `--adopt-remote` option is required. A future `--accept-attachment-change` option is
required to replace a known attachment hash and must report that Fact locators need review. Every
write uses an expected checksum, and every failure leaves no partial mutation.

### Workflow and future interfaces

Source workflow transitions are explicit and adjacent only:

```text
inbox -> reading -> processed -> integrated
```

Requesting the current stage is an idempotent success. Skips, regression, and transition beyond
`integrated` are contract errors.

The planned Phase 2A command targets are:

```text
kb source list [--type TYPE] [--stage STAGE] [--status STATUS] [--visibility VISIBILITY] [--json]
kb source show ID [--json]
kb source open ID
kb source sync ID [--adopt-remote] [--accept-attachment-change] [--json]
kb inbox [--json]
kb process ID --to reading|processed|integrated [--json]
```

`source list` and `inbox` scan durable files without SQLite. Source list sorts by updated descending
then ID ascending; inbox sorts by created ascending then ID ascending. Every command except
`source open` receives a versioned result schema inside CLI envelope v1 before implementation. The
planned syntax does not become an implemented or verified CLI surface merely because this ADR is
accepted; implementation must synchronize the CLI ledger and executable schemas.

The Paper capture service remains internal in Phase 2A. No public `kb add` command or paper-only
alias is registered before Phase 2B.

## Migration impact

The decision requires no v1 migration and does not invalidate existing Contract v2 Source files.
The future compatible v2 extension must preserve parse/render behavior for existing cards. New
Phase 2A-produced Sources use the richer fields and stricter automated-capture eligibility.

Any future incompatible representation, multiple-primary-attachment model, or change in the meaning
of existing durable fields requires a separate version and migration decision.

## Consequences

- Automated paper capture is deterministic but intentionally excludes Zotero-only items.
- Source identity survives Zotero item, attachment, path, and metadata changes.
- A missing PDF does not prevent bibliographic capture, while ambiguous or changed material is never
  guessed or silently trusted.
- Cross-device synchronization conflict detection depends on durable baseline metadata rather than
  disposable cache.
- The first implementation remains local-first and small; cloud Zotero access and multi-attachment
  selection can be added behind the same ports later.
- Phase 2A can test the paper backend without misleading users with a partial unified command.

## Alternatives considered

- Use Zotero key as canonical identity: rejected because adapter routes can change and do not merge
  the same work across libraries.
- Use title/author/year fingerprint for automatic identity: rejected because metadata changes and
  collisions would make idempotency unsafe.
- Require a PDF before creating a Source: rejected because metadata-only papers remain useful and a
  missing attachment is an availability issue, not an identity failure.
- Choose one of multiple PDFs by key, title, or modification time: rejected because the choice would
  be arbitrary and could invalidate locators.
- Store synchronization state only in `.knowlume`: rejected because cache loss or moving the Vault
  would erase the conflict baseline.
- Publish a paper-only `kb add` in Phase 2A: rejected by
  [`ADR-0009`](0009-unified-add-command.md), which releases all capture paths together in Phase 2B.
