# Storage, index, and search

> Status: Active  
> Baseline: v0.1  
> Authoritative for: durable storage, Git history, SQLite projection, indexing, and search behavior

## Durable and derived state

Tracked Markdown/YAML, schemas, templates, configuration, and code are durable. `kb.sqlite`, caches, temporary clones, derived output, logs, AI temporary output, and public staging are not durable knowledge.

```text
Markdown/YAML -> parser -> normalized projection -> SQLite
```

Deleting SQLite must never delete knowledge. A full rebuild must reproduce the same normalized objects, relations, sections, tags, visibility, and searchable text for the same contract/parser version.

## Git history

Git records changes to durable files. `kb history <id>` resolves an object by stable ID and projects relevant commits even when the file was renamed.

Human/agent attribution cannot be inferred reliably from prose alone. When required, commits use structured trailers or equivalent metadata. Sensitive material removed from the current tree may remain in Git history; incident handling and history rewriting are explicit administrative operations.

## SQLite projection

The first projection contains these logical surfaces:

| Surface | Purpose |
|---|---|
| `objects` | ID, kind/subtype, path, title, visibility, record/workflow state, timestamps, checksum |
| `relations` | source/target IDs, optional stable target section, type, locator, reason |
| `segments` | object and stable section IDs, provenance type, heading, text, source locator |
| `tags` / `object_tags` | normalized tag membership |
| `fts_segments` | title, text, tags, object ID, provenance type, visibility |
| metadata tables | schema/parser/tokenizer versions, scan state, parse errors, index timestamps |

Technical metadata is never the sole source of business facts.

## Build and rebuild

- `index build` incrementally handles additions, edits, renames, and deletions.
- `index rebuild` writes a new database transactionally and replaces the previous projection only after success.
- Checksums use normalized file bytes and a declared algorithm.
- Rebuild order is deterministic.
- Parse failures do not silently remove the last known object; they are reported and strict operations fail closed.
- Concurrent file changes are detected using checksum/mtime validation before committing an index transaction.

Rebuild acceptance compares normalized projection content, not SQLite row order or internal row IDs.

## Search levels

### L1: file search

`kb grep QUERY` scans the durable files directly. It requires no index and is the debugging baseline when projection results are questioned.

### L2: SQLite FTS5

`kb search QUERY` returns object ID/title, matching stable section, snippet/highlight, score, and superseded indication. Filters include object type, source type, tags, visibility, record/workflow state, and provenance section.

Machine consumers use the versioned JSON contract defined in [`interfaces.md`](interfaces.md).

### Chinese and English

SQLite's default tokenization is not a sufficient Chinese search specification. V1 uses a deterministic Python normalization/tokenization step and records its version in index metadata. A representative bilingual corpus must measure recall before choosing trigram or a specialized tokenizer.

### L3: semantic search

V1 defines a `SearchBackend` port but does not implement embeddings or a vector database. Semantic/hybrid search is a later adapter and must preserve the same visibility, AI-review, and provenance filters as file and FTS search.

## Context assembly

`kb context` composes results into Sources, Facts, My Notes, and Relevant Snippets. Context assembly does not bypass search or visibility policy. Trusted local/private and public-safe modes are explicit caller scopes, not inferred from output destination.

Security policy for context and publishing is authoritative in [`security-publishing.md`](security-publishing.md).

## Operational checks

`kb lint` verifies content contracts and projection consistency. `kb doctor` verifies runtime capabilities such as Python, Git, SQLite FTS5, Zotero access, vault configuration, and optional publishing tools. These responsibilities remain separate.
