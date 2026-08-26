# Roadmap and acceptance

> Status: Active  
> Baseline: v0.1  
> Authoritative for: implementation phases, scope, non-goals, delivery gates, and acceptance

Each phase begins only after the previous phase's executable gate passes. Detailed behavior belongs to the thematic documents linked from each phase.

## Current state

Phase 0 contract assets exist: versioned schemas, templates, valid/invalid fixtures, AGENTS rules, and executable tests. The current gate is green with 12 Phase 0 tests. Production parser and domain implementation are the next work item.

## Phase 0: contracts and boundaries

Deliverables:

- object, locator, relation, provenance, and visibility contracts;
- stable ID and section syntax;
- templates and positive/negative fixtures;
- repository and automation rules;
- executable schema and referential-integrity tests.

Gate: independent tools can read the same contract fixtures, invalid state/locator/relation cases fail, and no production implementation defines a conflicting rule.

## Phase 1A: parser, domain, and file scanner

Deliverables:

- immutable domain values and object models;
- Markdown/frontmatter parser with stable-section extraction;
- schema validation and typed parse errors;
- conflict-safe file reads/writes;
- filesystem scanner;
- `kb init`, `kb scan`, `kb status`, and baseline `kb lint`.

Gate: valid fixtures round-trip without identity loss, invalid fixtures produce typed errors, duplicate IDs are detected, and scanning uses Markdown/YAML without SQLite.

## Phase 1B: read-only management UI

Deliverables: loopback FastAPI service plus Dashboard, Sources, Notes, and Knowledge Health read views.

Gate: UI statistics derive from the same application services as CLI, with no independent business rules or write actions.

## Phase 2: source capture and Zotero

Deliverables: Zotero adapter, canonicalization, duplicate detection, `kb add`, inbox/process, source list/show/open/sync, and source-card generation.

Gate: paper/web/book/OSS capture is idempotent, returns to original material, emits no absolute machine path, and does not retain full OSS repositories as knowledge.

## Phase 3: SQLite FTS5 search

Deliverables: projection schema/migrations, transactional indexer, build/rebuild/status, file grep, FTS search/filters, bilingual normalization, snippets, and versioned JSON output.

Gate: deleting SQLite and rebuilding produces an equivalent normalized projection; file and FTS results can be explained against durable files.

## Phase 4: controlled automation and AI review

Deliverables: get/context/search JSON, harness examples, AI artifact storage/review/promotion, doctor, changed-file lint, and explicit context scopes.

Gate: automation receives traceable context and cannot silently move AI or private material across trust boundaries.

## Phase 5: evolution and publishing

Deliverables: backlinks/related/history, merge/supersede, tidy/organize/review, transitive publish audit, atomic staging, preview/build, Quartz adapter, and pre-commit integration.

Gate: evolution preserves IDs/history, and adversarial publish fixtures prove private and unreviewed dependencies are blocked.

## Phase 6: optional advanced capabilities

Evaluate only after earlier gates remain stable: semantic/hybrid search, embeddings, reranking, MCP facade, native editor/reference manager, browser extension, graph visualization, multi-agent reading, and external model routing.

## Command delivery batches

The command semantics are authoritative in [`interfaces.md`](interfaces.md).

1. Core: init, add, inbox, source show/open, note new, grep/search, index rebuild, status, lint, doctor, serve.
2. Evolution: tidy, related, backlinks, history, review, context, publish.
3. Advanced: organize, merge, supersede, AI promotion, semantic search.

## V1 non-goals

- video management;
- vector database, RAG pipeline, or semantic implementation;
- MCP server, graph database, graph visualization, multi-agent memory;
- custom PDF/EPUB reader or reference manager;
- browser extension or cloud synchronization service;
- durable full OSS clones or default Git storage of PDF/EPUB/Zotero storage;
- direct AI modification of facts;
- publishing by filtering the complete private vault;
- duplicated business logic in CLI and Web.

## Acceptance matrix

| Area | Required evidence |
|---|---|
| Data reliability | unique stable IDs, schema migration path, round-trip fixtures, deterministic rebuild |
| Provenance | facts resolve Source + locator; stable sections survive heading/file rename |
| AI | private/unreviewed default, explicit promotion audit, exclusion from default retrieval/publish |
| Sources | four source types validate; attachment recovery identifiers exist; OSS uses immutable commit |
| Interfaces | CLI/Web share services; JSON contract/version and typed exit codes are tested |
| Search | file baseline, FTS filters, bilingual corpus, explainable result-to-file mapping |
| Security | public dependency closure, path/symlink fixtures, sanitized rendering, redacted logs |
| Publishing | versioned audit manifest, atomic staging, preview, adversarial private/AI failures |

Executable schemas and current Phase 0 tests remain the acceptance authority for contract version 1. Checkboxes in older narrative documents do not override test results.
