# Storage, index, and search

> Status: Active — Contract v2
> Authoritative for: durable storage, Git history, SQLite projection, indexing, and search behavior

## Durable and derived state

The configured vault's Markdown/YAML objects and relation shards are durable facts. Schemas, templates, migrations, tests, configuration, and source code are durable repository assets. SQLite, caches, temporary clones, logs, AI scratch output, and public staging are disposable.

```text
vault Markdown/YAML -> parser -> normalized projection -> SQLite
```

Deleting SQLite must not delete knowledge. Given the same durable files and schema/parser/tokenizer versions, rebuilding produces the same normalized projection.

## Vault and writes

Program code and the personal vault are separate. Vault discovery follows the order defined in [interfaces](interfaces.md). Tracked Source cards and configuration never store machine-specific absolute paths.

Single-file writes use an expected checksum, a temporary file in the destination directory, flush, and atomic replacement. Multi-file operations use a vault lock, transaction manifest, and same-filesystem staging. Interrupted transactions must be detectable and recoverable or reversible. Phase 1 implements and tests equivalent observable behavior on Windows and Linux. Knowlume does not automatically commit, push, pull, or rewrite Git history.

## Git history

`kb history <id>` will resolve an object by stable ID across file renames. Identity and actor information cannot be inferred from prose or a filename; operations that need attribution record structured actor metadata.

## SQLite projection v2

The executable authority is [sqlite-projection-v2.sql](../schemas/v2/sqlite-projection-v2.sql). It projects object kind/subtype, maturity and review state, type transitions, relation shards and normalized locators, stable sections and roles, ordered segments, visibility/record/supersession state, and scan/version metadata.

Fact citations use a separate table so one content segment can retain multiple Source/locator pairs. Every FTS row carries enough identity to return deterministically to its segment, section, object, and provenance role. Files remain authoritative; row IDs and row order do not.

Rebuilds are deterministic and transactional. Parse failures are reported and cannot silently erase durable knowledge. Concurrent file changes are detected before a projection is committed.

Phase 3 stores the disposable database at `<vault>/<configured state>/kb.sqlite`. `index build`
creates it when absent and otherwise applies a checksum-based incremental transaction. `index
rebuild` validates a sibling temporary database before atomic replacement. Incompatible or corrupt
state is never silently replaced by a read or incremental command. The complete lifecycle, segment
algorithm, compatibility metadata, and diagnostics are frozen by
[`ADR-0016`](decisions/0016-phase3-deterministic-projection-search-context.md).

Note blocks are the stable input boundary for segments. Non-Note bodies use a reserved
projection-only `__body__` section key which is rendered as no durable section. Generated segment IDs
are deterministic for one segment-algorithm version but are disposable and never valid relation
targets. Rebuild determinism means equivalent normalized rows and stable IDs, not byte-identical
SQLite page layout or operational timestamps.

## Search surfaces

- File search and permanent-ID retrieval are index-independent trusted-local diagnostic baselines.
- FTS search supports filters for object kind/subtype, maturity/review state, visibility,
  record/supersession state, workflow stage, tags, and provenance role.
- Results are classified as Facts, Human Ideas/Interpretations, AI Inference, Evolution, or Snippets.
- Source-free human content remains searchable and may be public, but is represented as human opinion with empty citations, never as fact.
- Default local search includes active Source, human, fact, and Snippet content, including private
  content, and excludes archived, superseded, and AI results. Explicit AI search is trusted-local
  only and cannot bypass promotion rules.
- Missing, stale, incompatible, or corrupt indexes cannot serve FTS or context and are never rebuilt
  implicitly by a read command.

Tokenizer v1 uses standard-library Unicode NFKC and case folding, letter/number runs, and versioned
Han single-character plus adjacent-bigram tokens. Documents and literal queries use the same
pipeline. Semantic or hybrid search is deferred and must preserve the same visibility, provenance,
AI-review, and supersession filters.

## Context assembly

Context assembly returns traceable sections and citations under an explicit trusted-local or public-safe scope. It does not infer scope from a caller name or output destination and cannot bypass [publishing policy](security-publishing.md).

Phase 3 context groups Sources, Facts, Human Notes, and Snippets under a bounded character budget and
does not emit AI content. Public-safe scope audits each returned item's serialized dependency closure,
excludes unsafe candidates with typed reasons, and retains safe candidates. This result is not a
Phase 6B publish audit or staging manifest.
