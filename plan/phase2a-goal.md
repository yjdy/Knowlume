# Phase 2A execution goal: Paper and Zotero

> Status: Complete — local, distribution, isolated-install, and cross-platform gates green
> Target: complete the Paper/Zotero vertical slice without exposing the Phase 2B `kb add` command

## 1. Outcome

Phase 2A delivers a canonical and idempotent internal Paper capture service, a read-only Zotero
Local API adapter, recovery of one primary PDF, Source browsing and synchronization, and explicit
Source workflow transitions. It builds on the Phase 1 Vault, scanner, parser, and safe-write
protocol and does not depend on SQLite.

At the end of the phase:

- DOI and arXiv inputs are normalized into stable Paper identity requests, and the internal capture
  service creates an idempotent Source after an injected metadata resolver returns eligible data;
- repeated capture returns the existing Source ID and creates no duplicate durable file;
- Zotero metadata can be recovered and synchronized without reading `zotero.sqlite`;
- one primary PDF can be recovered through Zotero without storing an absolute path or attachment
  body in the Vault;
- `source list/show/open/sync`, `inbox`, and `process` satisfy their command-level gates;
- failures and conflicts leave no partial Source, relation, transaction, or accepted scan result;
- the public `kb add` command remains absent until all Phase 2B capture backends pass together.

The accepted decisions are frozen by
[`ADR-0012`](decisions/0012-phase2a-paper-zotero-design.md), with the completed implementation
boundary and acceptance evidence clarified by
[`ADR-0014`](decisions/0014-phase2a-acceptance-and-phase2b-zotero-classification.md). Source
semantics belong to
[`data-model.md`](data-model.md), adapter behavior to
[`sources-and-adapters.md`](sources-and-adapters.md), future interface behavior to
[`interfaces.md`](interfaces.md), and sequencing to [`roadmap.md`](roadmap.md).

### Completion clarification

Phase 2A does not include a production DOI/arXiv-to-Zotero search resolver. Its production Zotero
adapter reads metadata from an exact `ZoteroReference`; tests inject the `PaperMetadataPort` used by
the internal capture service. Automatic personal-library candidate search and Zotero Paper/Book
`itemType` classification are Phase 2B work. This clarification does not invalidate Phase 2A or
retroactively reclassify an existing exact-reference Paper Source.

The original cross-platform and distribution gates remain valid. Direct CLI regression tests now
also cover every published Source filter, successful and failed open behavior, explicit sync
approval options, warning envelopes, and the principal human-readable renderers. Phase 2A remains
Complete/Verified; the `Phase2A` tag is historical and is not moved.

## 2. Non-negotiable requirements

### Identity and capture eligibility

- A Source ID is the permanent domain identity. DOI, arXiv, and Zotero values are external
  identifiers or recovery routes and never replace it.
- Phase 2A automated capture requires a normalized DOI or arXiv ID. A Zotero-only item is reported
  as ineligible and writes nothing.
- Existing Contract v2 Sources that use only a Zotero recovery route remain readable. This
  compatibility does not authorize the Phase 2A capture service to create more of them.
- DOI is the preferred canonical external identity when both DOI and arXiv are present. Matching
  either identifier finds the existing Source; identifiers resolving to different Sources are a
  blocking conflict and are never auto-merged.
- arXiv base identity ignores the optional `vN` suffix. The captured version and attachment hash
  preserve the exact recovered material.

### Zotero and attachments

- Phase 2A uses only Zotero's supported loopback Local API and performs read operations only.
- Production code never reads Zotero's private SQLite database and never accepts a non-loopback
  endpoint for this adapter.
- The first slice manages at most one primary PDF. Zero candidates produces a typed availability
  warning; multiple candidates produce an ambiguity warning; neither case guesses a file.
- A recoverable primary PDF records adapter identifiers and integrity metadata, not a machine path.
- A changed attachment hash is a provenance conflict. Ordinary synchronization cannot silently
  replace the recorded material or invalidate existing Fact locators.

### Synchronization and ownership

- Human-owned fields are never overwritten by Zotero. Adapter-owned bibliographic fields are
  updated only when the stored synchronization baseline still matches the current Source.
- Source cards retain the Zotero item version, synchronization time, and a deterministic hash of
  adapter-managed fields so conflict detection survives cache deletion and movement to another
  computer.
- Identity removal or replacement, identifier collision, local managed-field edits, attachment
  replacement, checksum conflict, and unavailable adapter state all fail before a durable write.
- No-op synchronization is successful and byte-preserving. Every actual mutation uses the Phase 1
  expected-checksum and atomic-write protocol.

### Workflow and machine interfaces

- Workflow transitions are explicit and adjacent only:
  `inbox -> reading -> processed -> integrated`.
- A request for the current stage is idempotent. Skipping, regression, or transition beyond
  `integrated` is rejected.
- `source list`, `source show`, `source sync`, `inbox`, and `process` receive versioned JSON result
  schemas before their `--json` options are implemented. `source open` remains human-facing.
- The planned result contracts are `source-list-result-v1`, `source-show-result-v1`,
  `source-sync-result-v1`, and `source-workflow-result-v1`; inbox reuses the Source-list result.
- Durable-file scans back Source queries in Phase 2A. SQLite is not a write prerequisite or query
  authority.

## 3. Milestones and Git checkpoints

### M0 — Freeze executable contracts

Record the accepted decision, then update the compatible Contract v2 schema, current template,
positive and negative fixtures, interface schemas, and executable contract tests. Planned additive
concepts include arXiv identity/version, Zotero library and item version, synchronization baseline,
and primary-attachment integrity metadata. Exact machine fields become authoritative only when the
versioned schemas are updated.

Completion requires old Contract v2 fixtures to remain readable, new fixtures to enforce the
Phase 2A rules, and no Contract v1 change.

**Git commit:** Yes — P2A-C1, suggested message:
`docs(contract): freeze phase 2a paper and zotero contracts`.

### M1 — Implement Paper domain values and ports

Implement DOI/arXiv normalization, canonical external identity, alias-aware duplicate detection,
identity-collision findings, Paper metadata requests/results, and ports for Zotero metadata and
primary-attachment recovery. Adapter response types must not enter the domain layer.

Completion requires deterministic normalization and collision tests, including DOI URL forms,
old/new arXiv forms, optional versions, matching aliases, and split-identity conflicts.

**Git commit:** Yes — P2A-C2, suggested message:
`feat(paper): add canonical identity and capture ports`.

### M2 — Implement the Zotero Local API adapter

Implement a loopback-only API v3 client, exact-reference library/item mapping, one-primary-PDF
selection, disposable cache recovery, content hashing, timeout handling, and typed
unavailable/permission/malformed-data errors. Keep adapter dependencies optional and fail with a
capability diagnostic when the Zotero extra is absent.

Completion requires mock-server coverage for disabled API, timeout, permission failure, missing
item, malformed response, zero/one/multiple PDFs, cache reuse, and hash mismatch.

**Git commit:** Yes — P2A-C3, suggested message:
`feat(zotero): add local paper metadata and attachment adapter`.

### M3 — Implement internal Paper capture

Implement the application flow:

```text
normalize -> resolve metadata -> canonical identity -> duplicate check
          -> Source construction -> attachment recovery -> atomic write -> scan
```

The service accepts a DOI, arXiv identifier, or Zotero recovery reference internally, but it writes
only when resolved metadata contains DOI or arXiv identity. Repeated capture returns the existing
Source ID. Every failure before acceptance leaves no partial durable state.

Completion requires idempotency, collision, adapter failure, write conflict, interruption, and
post-write scan tests. No public `kb add` registration is allowed.

**Git commit:** Yes — P2A-C4, suggested message:
`feat(paper): add idempotent internal capture service`.

### M4 — Implement Source and workflow commands

Implement scanner-backed Source list/show, Zotero-backed open/sync, inbox listing, and explicit
workflow transition services. Add the planned JSON schemas and synchronize `CLI.md` in the same
implementation change before exposing any new option.

Completion requires stable ordering, human and JSON rendering, exact exit behavior, no-op
idempotency, baseline adoption, local-edit conflict, identity conflict, attachment-change handling,
and expected-checksum tests.

**Git commit:** Yes — P2A-C5, suggested message:
`feat(cli): add phase 2a source and workflow commands`.

### M5 — Pass the Phase 2A gate

Run the complete repository suite, Ruff, mypy, distribution audit, isolated-wheel smoke tests, and
Windows/macOS/Linux Python 3.13–3.14 CI. Audit the installed package with and without the Zotero
extra. Only after all evidence is green may README, roadmap, and CLI status move to Phase 2A
Complete/Verified.

**Git commit:** Yes — P2A-C6, suggested message: `docs: mark phase 2a complete`. This commit contains
status declarations only and must be reverted if supporting evidence is invalidated.

## 4. Limits

- No public or partial `kb add`; the unified router remains Phase 2B.
- No Web, Book, OSS, Snippet, SQLite projection/search, Web UI, cloud Zotero API, OAuth, Zotero
  mutation, supplementary attachment selection, or automatic Fact-locator rewrite.
- No machine-specific absolute path, credential, token, attachment body, Zotero storage path,
  database, cache, or temporary file becomes durable Vault content.
- No package install, update, downgrade, or uninstall operation may capture, sync, or migrate a
  Source.
- No Git commit, push, tag, package upload, or release is implicit in a phase milestone.

## 5. Completion checks

The Phase 2A gate requires direct automated evidence for:

- DOI and arXiv normalization, version handling, alias matching, conflict detection, and repeated
  capture through an injected metadata resolver;
- rejection of newly captured Zotero-only papers while preserving old readable v2 Sources;
- Zotero disabled, unavailable, timeout, permission, missing-item, and malformed-response cases;
- zero, one, and multiple PDF candidates; integrity match, mismatch, and explicit acceptance;
- adapter-field updates, human-field preservation, first baseline adoption, local edits, identity
  changes, no-op synchronization, checksum conflicts, and interruption recovery;
- Source list/show/open/sync, inbox, and every workflow transition, including filters, explicit sync
  approvals, human output, warning behavior, and JSON golden output wherever specified;
- absence of absolute paths, credentials, attachment bodies, partial writes, SQLite dependency, and
  a registered public `kb add` command;
- core-wheel operation without Zotero dependencies and installed-wheel behavior from an arbitrary
  working directory.

Required final commands are:

```powershell
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests scripts
uv run --no-sync mypy src tests scripts
```

Packaging verification follows [`distribution.md`](distribution.md). TestPyPI remains an
independent, explicitly authorized Release-track action and is not a Phase 2A feature gate.
