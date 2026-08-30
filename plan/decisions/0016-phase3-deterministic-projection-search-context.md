# ADR-0016: Freeze Phase 3 deterministic projection, search, and context behavior

- Status: Accepted
- Date: 2026-08-29
- Decision owners: Knowlume maintainers

## Context

Phase 2B is complete and merged. Knowlume can create and validate Contract v2 Sources, Notes,
Snippets, AI Artifacts, and relation shards, but every production query still scans durable files.
The repository already contains projection DDL v2 and requires SQLite to remain disposable, yet it
does not freeze the database location, segment construction, bilingual tokenizer, index lifecycle,
search defaults, context safety, or Phase 3 machine results.

These choices affect deterministic rebuilds, package compatibility, privacy, and every later CLI,
Web, and automation reader. They must be decided before interface schemas or production code are
added. Phase 3 must reuse the current parser/scanner and application/port/adapter boundaries rather
than creating a second interpretation of Contract v2.

## Decision

### Derived-state location and ownership

The projection database is `<vault>/<configured state>/kb.sqlite`, resolved as
`vault.path("state") / "kb.sqlite"`. The existing portable configuration already identifies the
state directory, so Phase 3 does not add a configuration field or change configuration version 1.
The database, its temporary siblings, journals, locks, and recovery metadata are disposable and
must never become the only source of a fact.

`kb index build` creates a full index when the database is absent. With a compatible database it
performs an incremental update. It does not silently replace an incompatible or corrupt database;
the caller must use `kb index rebuild`. Search and context never create or repair an index.

A rebuild creates a sibling temporary database, applies the bundled projection DDL through
`importlib.resources`, projects a healthy scanner snapshot, validates foreign keys and integrity,
closes every SQLite handle, and atomically replaces `kb.sqlite`. Scanner errors, unsafe paths,
concurrent durable-file changes, or database validation failures leave the previous database
unchanged. An index-only lock under the configured state directory is acquired non-interactively;
contention returns `INDEX_BUSY` and does not wait indefinitely or take the durable-write lock.

### Scanner snapshot and normalized projection

`scan_vault` output is the only production input to projection. The indexer may transform normalized
domain values into rows, but it must not parse Markdown, YAML, frontmatter, citations, locators, or
relations independently.

Projection order is deterministic: vault-relative path, object ID, durable section ordinal, block
ordinal, citation ordinal, and canonical relation key. Locators and other structured values are
stored as UTF-8 canonical JSON with sorted keys, compact separators, normalized domain values, and
no absent optional fields.

Note sections use their durable `section_id`. Each Note block becomes one segment and retains the
section role, block ordinal, citations, and promoted Artifact reference when applicable. Non-Note
objects use the reserved projection-only section key `__body__`:

| Object | Projection role | Segment content |
|---|---|---|
| Source | `source` | normalized body after frontmatter |
| Snippet | `snippet` | normalized body after frontmatter |
| AI Artifact | `ai` | normalized body after frontmatter |

Durable Note sections and blocks use zero-based ordinals in scanner order. Each non-Note object has
exactly one `__body__` projection section with heading `__body__`, section ordinal `0`, and one body
segment at ordinal `0`. The sentinel is stored only to satisfy projection joins. Public results
render its `section_id` as `null`; it is not a durable Section ID and cannot be used by relations.

Segment algorithm v1 derives:

```text
segment_id = "seg_" + sha256(
  utf8("segment-v1\0" + object_id + "\0" + section_key + "\0" + decimal(block_ordinal))
).hexdigest()
```

Segment IDs are deterministic projection keys, not durable identities. A rebuild may change them
only after an explicit segment-algorithm version change. They must never be written to a Vault file,
used as a relation target, or exposed as a substitute for object and durable section identity.

Deterministic rebuild means row-equivalent content tables, stable metadata, ordering, IDs, and
normalized values for the same durable bytes and contract/parser/tokenizer versions. SQLite file
bytes, page layout, build time, scan time, and other documented operational timestamps need not be
identical.

Projection DDL v2 is sufficient for this behavior. Phase 3 does not change it or increment
`PROJECTION_VERSION`. If implementation proves that the DDL cannot represent a required invariant,
work stops for a separate projection-version and migration decision; the v2 DDL is not edited in
isolation.

### Version and compatibility metadata

Phase 3 adds `TOKENIZER_VERSION = 1` as an independent runtime version and includes it in
`kb --version`. A compatible index records at least:

- projection, object, locator, relation, parser, tokenizer, and segment-algorithm versions;
- the deterministic source snapshot hash derived from sorted `(path, checksum)` pairs;
- the last successful build time as operational metadata.

A mismatch in any interpretation-affecting version is `INDEX_INCOMPATIBLE`. A path/checksum set that
does not match the current durable snapshot is `stale`. Search and context fail closed for both
states. Version changes require an explicit rebuild, not an in-place reinterpretation of existing
rows.

### Tokenizer v1

Tokenizer v1 uses only the Python standard library. It adds no word-segmentation, model, native, or
network dependency.

Both indexed fields and queries follow the same pipeline:

1. normalize with Unicode NFKC and `casefold()`;
2. retain contiguous non-Han Unicode letter/number runs as ordinary tokens;
3. split punctuation, symbols, control characters, and whitespace;
4. for each contiguous Han run, emit all characters in source order, followed by all adjacent
   two-character n-grams in source order;
5. discard empty tokens and preserve repeated token positions for FTS ranking.

The version-1 Han table contains the Unicode blocks named CJK Unified Ideographs, Extensions A-J,
CJK Compatibility Ideographs, and CJK Compatibility Ideographs Supplement as listed by the Unicode
Character Database `Blocks.txt` at the time of this decision. The exact inclusive ranges are:

```text
3400-4DBF, 4E00-9FFF, F900-FAFF,
20000-2A6DF, 2A700-2B73F, 2B740-2B81F, 2B820-2CEAF,
2CEB0-2EBEF, 2EBF0-2EE5F, 2F800-2FA1F,
30000-3134F, 31350-323AF, 323B0-3347F
```

Changing normalization, ranges, token boundaries, or emitted n-grams requires a tokenizer-version
bump and rebuild. Queries are literal text: the application generates quoted FTS terms and never
passes caller-provided FTS5 syntax through unchanged.

### Index build, refresh, and status

`index build` compares the current scanner snapshot with `scan_state`, then inserts, updates, and
deletes affected object and relation rows in one SQLite transaction. A missing database takes the
same full-build path as rebuild but does not overwrite an existing incompatible or corrupt file. A
no-op does not rewrite content rows.

After Phase 3, every successful durable mutation requests an incremental refresh only when a
compatible index already exists. Durable data commits first. Refresh failure never rolls back a
successful durable write; it returns a stable warning and the next status check reports the index as
stale. Index absence is not a write failure and does not cause implicit index creation.

`index status` distinguishes `missing`, `fresh`, `stale`, `incompatible`, and `corrupt`, and reports
versions, source snapshot, counts, changed paths, and typed findings without repairing state.
Relative paths only are returned. A corrupt SQLite file is never attached or copied into durable
output.

### Search, retrieval, and machine interfaces

Phase 3 exposes:

```text
kb grep QUERY [--limit N] [--json]
kb get ID [--json]
kb index build [--json]
kb index rebuild [--json]
kb index status [--json]
kb search QUERY [filters] [--scope trusted-local|public-safe] [--limit N] [--json]
kb context QUERY --scope trusted-local|public-safe [--limit N] [--max-chars N] [--json]
```

`grep` and `get` are index-independent. `grep` is a trusted-local diagnostic over configured durable
object and relation roots, returns relative path plus ephemeral line/column navigation, and does not
claim that a line number is durable identity. `get` resolves a permanent object ID and returns its
normalized object, body, path, checksum, citations, and relations.

Search filters are kind, subtype, visibility, record status, workflow stage, maturity, review status,
tag, and provenance role. Repeated tags use AND semantics. Default limit is 20 and the maximum is
200. Ranking uses SQLite FTS5 BM25 followed by object ID, public section ID or empty value, and
segment ordinal as deterministic tie-breakers.

The default CLI search scope is `trusted-local`. It includes private and public active Sources,
human blocks, fact blocks, and Snippets. It excludes archived and superseded objects, AI Artifacts,
and AI segments. AI may be returned only under `trusted-local` after an explicit AI kind/role filter;
an AI block inside a Note must still reference a promoted Artifact. `public-safe` never widens these
rules.

All seven Phase 3 commands support `--json` and reuse CLI envelope v1. Their data shapes are owned by
new `grep-result-v1`, `get-result-v1`, `search-result-v1`, `context-result-v1`, and
`index-result-v1` schemas. JSON contains only vault-relative paths. Search hits include enough data
to explain object, path, durable Note section when present, projection segment, role, snippet, score,
and citations.

### Context assembly and public-safe scope

`kb context` requires `--scope`; omission is a usage error. Default maximum output is 12,000 Unicode
characters. Results are ordered deterministically and grouped as Sources, Facts, Human Notes, and
Snippets. Phase 3 context does not emit AI content.

`trusted-local` may include private content on the local machine. `public-safe` audits each proposed
output item before inclusion:

- the returned object is public, active, and not superseded;
- Fact citations resolve to public, active Sources with valid, type-matched locators;
- Web snapshot, Book edition/ISBN, and OSS host/path/commit provenance remain coherent;
- Snippets are public, publication-approved, linked to a public eligible Source, and have resolved
  license evidence rather than `NOASSERTION`;
- no unpromoted AI body or private Artifact body is emitted;
- every dependency serialized into this context is itself eligible.

Unsafe candidates are excluded individually and reported with typed reasons; safe candidates remain
available. This is a complete audit of the returned context, not a Phase 6B declaration that an
object, Vault, or site is publishable. Full public allowlist closure and staging remain Phase 6B.

### Diagnostics

Phase 3 reserves these public diagnostics and existing CLI exit meanings:

| Code | Exit | Meaning |
|---|---:|---|
| `INDEX_NOT_FOUND` | 5 | a command requires an index and none exists |
| `INDEX_INCOMPATIBLE` | 3 | index interpretation versions do not match runtime versions |
| `INDEX_CORRUPT` | 3 | SQLite cannot be opened or does not pass required integrity checks |
| `INDEX_SOURCE_INVALID` | 3 | durable input does not produce a healthy scanner snapshot |
| `INDEX_SOURCE_CHANGED` | 4 | durable paths or checksums changed before projection commit |
| `INDEX_BUSY` | 4 | another projection writer owns the index lock |
| `SEARCH_QUERY_INVALID` | 2 | the query or filters cannot form a supported literal search |
| `OBJECT_NOT_FOUND` | 3 | `kb get` cannot resolve the requested permanent object ID |

Best-effort post-write refresh failure is a warning using `INDEX_REFRESH_FAILED`; it does not change
the successful mutation exit code. Internal SQLite messages, absolute paths, SQL text, private body
content, and temporary filenames are not exposed through public diagnostics.

## Migration and release impact

No durable object, locator, relation, Note-body, configuration, or transaction contract changes.
Contract v1 remains read-only, Contract v2 files need no migration, configuration stays at v1, and
projection DDL stays at v2. Existing or future SQLite files are disposable and are upgraded only by
explicit rebuild.

Phase 3 adds interface result schemas at version 1 and an independent tokenizer version. Package
installation, upgrade, downgrade, and removal do not create, rebuild, or delete a Vault index.

After all Phase 3 feature, distribution, isolated-install, and supported-platform gates pass—and
only after the release owner proves control of the normalized PyPI project name—the repository may
open both `testpypi-enabled` and `pypi-prerelease-enabled`. `pypi-stable-enabled` remains false.
Opening gates does not authorize a version change, tag, upload, GitHub Release, or publication.

## Consequences

- Search remains reproducible without a native tokenizer or external model.
- The n-gram strategy favors predictable recall and cross-platform installation over linguistic word
  boundaries; a tokenizer-version bump can replace it later.
- File search and object retrieval remain available when SQLite is missing or unhealthy.
- Search never silently serves known-stale or incompatible results.
- Durable writes do not become dependent on disposable index availability.
- Public-safe context is useful before Phase 6B without weakening the later publish boundary.
- Projection-only segment and body-section keys cannot leak into durable identity semantics.

## Alternatives considered

- Store `kb.sqlite` at the Vault root: rejected because the configured state directory already owns
  disposable locks and transaction state.
- Store the index in the system cache directory: rejected because Vault-to-cache identity and cleanup
  become machine-specific and harder to inspect.
- Use [`jieba`](https://pypi.org/project/jieba/),
  [`rjieba`](https://pypi.org/project/rjieba/), or
  [`jieba3`](https://pypi.org/project/jieba3/): rejected for tokenizer v1 because legacy
  compatibility metadata, native-wheel dependency, or additional runtime dependency weight would
  expand the core cross-platform gate.
- Use SQLite's trigram tokenizer: rejected because short one- and two-character searches require
  separate behavior and SQLite build/runtime behavior would own part of the language contract.
- Auto-rebuild during search: rejected because a read command must not hide a potentially expensive
  or destructive derived-state mutation.
- Commit a partial rebuild after parse failures: rejected because missing or invalid durable content
  could silently disappear from ordinary search.
- Default to public-only or include all AI/superseded content: rejected because neither matches a
  trusted local knowledge workflow with explicit provenance controls.
- Treat Phase 3 public-safe context as a publish audit: rejected because Phase 6B owns full allowlist
  closure, staging, and release evidence.
