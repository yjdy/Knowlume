# ADR-0014: Reconcile Phase 2A acceptance and freeze Phase 2B Zotero classification

- Status: Accepted
- Date: 2026-08-29
- Decision owners: Knowlume maintainers

> Phase 2B Web/Book/OSS provenance coherence and anonymous Git resolution are frozen separately by
> [`ADR-0015`](0015-phase2b-provenance-and-anonymous-git.md).

## Context

Phase 2A delivered DOI/arXiv normalization, an internal Paper capture service behind an injectable
metadata port, exact Zotero item recovery, primary-PDF handling, Source commands, and Paper
synchronization. Its completion wording could also be read as claiming a production DOI/arXiv
search resolver. No such resolver exists: the production Zotero adapter reads an exact
`ZoteroReference`, while tests inject `PaperMetadataPort` implementations.

Phase 2A also did not use Zotero `itemType` to decide whether an item was a Paper. Phase 2B must add
automatic personal-library search and distinguish Paper from Book before the unified `kb add`
command can be deterministic. The completed Phase 2A Source commands additionally need direct CLI
evidence for every published option and a complete stable diagnostic ledger.

## Decision

### Phase 2A boundary and compatibility

Phase 2A remains Complete and Verified. Its implemented Paper boundary is:

- DOI/arXiv parsing and normalization;
- canonical Paper identity and alias collision handling;
- an internal idempotent capture service using an injected `PaperMetadataPort`;
- read-only metadata and attachment recovery from an exact Zotero reference;
- scanner-backed Source commands, Paper synchronization, and attachment integrity checks.

Production DOI/arXiv-to-Zotero candidate search and Paper/Book classification belong to Phase 2B.
This clarification does not move or replace the `Phase2A` tag and does not rewrite history.

Existing Paper Sources remain readable, openable, and synchronizable by their stored DOI/arXiv and
exact Zotero references. Phase 2B item-type eligibility applies only to new unified capture and does
not retroactively reclassify or invalidate an existing Paper Source.

### Phase 2B Zotero item classification

Automatic Zotero search is limited to the personal `users/0` library. Quick search narrows the
candidate set; every returned item is re-normalized and matched exactly by DOI, arXiv, ISBN, or URL.
Candidate order is never a selection rule.

A newly captured Paper accepts only these top-level Zotero item types:

- `journalArticle`;
- `conferencePaper`;
- `preprint`;
- `thesis`;
- `report`;
- `manuscript`.

A newly captured Book accepts only top-level `book`. `bookSection`, a missing `itemType`, and every
other item type are ineligible for automatic Paper or Book capture.

For a DOI without an explicit type, exactly one exact candidate must classify unambiguously as
Paper or Book. Zero candidates, multiple exact candidates, mixed classifications, or only
unsupported item types produce `ADD_TYPE_AMBIGUOUS` with exit code 3. With an explicit
`--type paper` or `--type book`, zero candidates, multiple exact candidates, or an incompatible item type
produce `ADD_METADATA_UNAVAILABLE` with exit code 5.

### Explicit type input shapes

`--type` selects recognition only and never bypasses metadata or safety checks:

| Explicit type | Accepted input shape | Incompatible shape |
|---|---|---|
| `paper` | DOI or arXiv identifier/URL | `ADD_INPUT_INVALID` (2) |
| `book` | DOI or checksum-valid ISBN | `ADD_INPUT_INVALID` (2) |
| `web` | credential-free HTTP(S) URL | `ADD_INPUT_INVALID` (2) |
| `repo` | credential-free HTTP(S) repository-root candidate | `ADD_INPUT_INVALID` (2) |

On success, `requested_type` and `detected_type` both contain the explicit CLI type. Without an
override, `detected_type` contains the final type selected after metadata or remote resolution.

### Identity conflicts and public diagnostics

`ADD_IDENTITY_CONFLICT` is a stable Phase 2B diagnostic with exit code 3. It covers DOI/arXiv,
DOI/ISBN, or cross-Paper/Book aliases that resolve to different Source IDs. Concurrent durable-file
change remains `ADD_WRITE_CONFLICT` with exit code 4.

All errors and warnings reachable through a published CLI command are stable machine-interface
codes and must be listed in `interfaces.md` with their exit or warning severity. Shared Phase 1
Vault, parsing, object-ID, and security diagnostics are referenced from their existing authority
rather than duplicated. Adapter-construction and internal capture invariant errors remain internal
unless a public command exposes them; `kb add` must translate such failures into its stable
`ADD_*` vocabulary.

## Migration impact

There is no object-contract, configuration, or machine-interface version migration. Existing v2
Sources and existing Phase 2A JSON result schemas remain valid. `ADD_IDENTITY_CONFLICT` is added
before the Phase 2B `kb add` interface is released.

## Consequences

- Phase 2A completion describes implemented production wiring rather than a future resolver.
- Phase 2B owns a concrete, conservative Zotero classification rule.
- Existing exact-reference Paper workflows remain backward compatible.
- CLI verification must cover registered options, human output, JSON output, warnings, and exact
  exit codes before a command is marked Verified.
- New scholarly Zotero item types require a later accepted decision instead of silent broadening.

## Alternatives considered

- Treat every non-Book DOI item as Paper: rejected because Web and other Zotero item types can carry
  DOI-like metadata and automatic capture must not guess.
- Make the Paper item-type list configurable in Phase 2B: rejected to keep the first public capture
  contract deterministic and small.
- Retroactively enforce item types during Phase 2A sync: rejected because it could invalidate
  previously accepted exact-reference Paper Sources.
- Downgrade Phase 2A from Complete: rejected because the implemented features exist; the defect is
  an over-broad completion sentence and incomplete command-level evidence, both repaired by an
  explicit erratum and regression tests.
