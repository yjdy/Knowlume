# Roadmap and acceptance

> Status: Active — Contract v2
> Authoritative for: implementation phases, delivery gates, command ownership, and non-goals

Each phase starts only after the preceding executable gate is green. Thematic documents own behavior; this file owns sequencing.

## Current state

Phase 0R is complete: Contract v1 is archived and executable for history/migration, Contract v2 is the sole production target, and v2 decisions, schemas, templates, fixtures, migration contract, SQLite projection, and acceptance tests are in place. Phase 1 is next. No production `kb` package, CLI, migration program, database, or Web service exists yet.

## Phases and gates

| Phase | Deliverables | Gate |
|---|---|---|
| 0R — Contract v2 | ADRs, versioned schemas/templates/fixtures, migration report, projection DDL, contract/link tests | v1 remains executable; v2 positive/negative and migration cases pass; DDL and interface surfaces are frozen |
| 1 — Vault and core | vault discovery, domain values, parser/scanner/lint, safe single/multi-file writes, Note creation/evolution | ID/section round-trip, typed errors, conflict detection, and crash recovery pass on Windows/Linux |
| 2A — Paper/Zotero slice | paper capture, canonicalization, Zotero metadata/attachment recovery | capture is idempotent; attachment and locator recovery pass without absolute tracked paths |
| 2B — Web/Book/OSS | snapshots, edition identity, immutable commits, snippet/license review | source-specific locator and publication fixtures pass |
| 3 — Projection/search | SQLite rebuild/index, FTS, bilingual normalization, context assembly | deleting SQLite and rebuilding is deterministic; every FTS hit returns to durable segment/section |
| 4 — Read-only Web | loopback Dashboard, Sources, Notes, Search, health views | Web and CLI share services and business rules; Web has no mutations |
| 5 — Automation/AI | machine context, AI review/promotion, explicit scopes, doctor | AI cannot cross review, privacy, or provenance boundaries |
| 6A — Evolution | merge, supersede, history, backlinks, review/tidy suggestions | IDs, actors, relations, and history remain complete |
| 6B — Publishing | closure audit, atomic staging, preview/build, Quartz adapter | adversarial private, AI, path, and rights cases fail closed |
| 7 — Advanced | semantic/hybrid search, MCP, graph, multi-agent workflows | evaluated only after earlier gates remain stable |

## Command → phase → gate matrix

| Commands/capability | Phase | Required gate evidence |
|---|---:|---|
| contract/schema validation | 0R | versioned positive/negative fixtures and documentation links pass |
| `init`, `scan`, `status`, `lint`, `note new/evolve`, `relation add/remove/list`, `migrate` | 1 | vault, parser, identity, atomicity, conflict, recovery, and migration tests |
| `add paper`, `source list/show/open/sync`, inbox/process | 2A | canonical and idempotent Zotero slice |
| `add web/book/repo`, `snippet add` | 2B | snapshot, edition, commit/range/license checks |
| `grep`, `search`, `index`, `get`, `context` | 3 | deterministic projection and result-to-file explanation |
| `serve` read views | 4 | shared-service parity and local-service security |
| `ai list/review/promote`, automation JSON, `doctor` | 5 | promotion audit and explicit-scope tests |
| related/backlinks/history, merge/supersede, tidy/organize/review | 6A | identity and history preservation |
| `publish audit/build/preview` | 6B | complete closure and adversarial staging tests |

This matrix is the only delivery-batch authority.

## Deferred scope

Phase 7 includes vector/RAG implementation, MCP, graph databases/visualization, multi-agent memory, native readers/reference managers, browser extensions, and cloud synchronization. Full OSS clones, private attachment collections, generated public output, and direct AI modification of trusted facts are never default durable content.

## Acceptance dimensions

Contract changes require versioning and migration evidence. Durable identities survive rename and evolution. Facts resolve all Source/locator citations. AI promotion remains auditable. Search returns to durable segments. Public builds prove complete closure, isolation, and fail-closed behavior. Actual tests and CI results—not manually maintained test counts—are the status authority.
