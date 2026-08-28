# Roadmap and acceptance

> Status: Active — Contract v2
> Authoritative for: implementation phases, delivery gates, command ownership, and non-goals

Each phase starts only after the preceding executable gate is green. Thematic documents own behavior; this file owns sequencing.

## Current state

Phase 0R, Phase 1, and Phase 2A are complete. Phase 2A passed local, distribution,
isolated-install, and Windows/macOS/Linux Python 3.13–3.14
[CI](https://github.com/yjdy/Knowlume/actions/runs/33179444723) and
[package smoke](https://github.com/yjdy/Knowlume/actions/runs/33179444644) gates. Phase 1 passed
local, distribution, isolated-install, and
Windows/macOS/Linux Python 3.13–3.14 [CI](https://github.com/yjdy/Knowlume/actions/runs/33120979913)
and [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33120979856) gates. Database,
unified capture/search, and Web work remain in their later phases; publication gates remain closed.

## Release track

Release engineering runs across the feature phases without advancing their gates:

| Gate | Distribution outcome |
|---|---|
| Foundation | pure-Python wheel/sdist, bundled resource audit, `--version`, package `doctor`, explicit `update-check`, three-platform CI |
| Phase 1 complete | manually approved TestPyPI internal package |
| Phase 3 complete | first public PyPI prerelease and matching GitHub Release |
| Phase 6B complete | stable `1.0.0` or later |

Publishing remains blocked until the release owner controls the normalized PyPI project name. Package installation, upgrade, downgrade, and removal never migrate or delete a vault.

## Phases and gates

| Phase | Deliverables | Gate |
|---|---|---|
| 0R — Contract v2 | ADRs, versioned schemas/templates/fixtures, migration report, projection DDL, contract/link tests | v1 remains executable; v2 positive/negative and migration cases pass; DDL and interface surfaces are frozen |
| 1 — Vault and core | vault discovery, domain values, parser/scanner/lint, safe single/multi-file writes, Note creation/evolution | ID/section round-trip, typed errors, conflict detection, and crash recovery pass on Windows/Linux |
| 2A — Paper/Zotero slice | internal paper capture service, DOI/arXiv canonicalization, read-only Zotero Local API, one-primary-PDF recovery, Source query/sync/workflow | capture is canonical, idempotent, conflict-safe, and failure-atomic; attachment recovery has integrity evidence without tracked absolute paths; planned Source commands pass; no public `kb add` is exposed |
| 2B — Unified capture | web/book/OSS adapters, snapshots, edition identity, immutable commits, snippet/license review, public `kb add` router | all four recognition paths, explicit override, idempotency, failure atomicity, and add-result JSON pass alongside source-specific locator/publication fixtures |
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
| `--version`, package `doctor`, `update-check` | Release foundation | command tests, wheel resource/content audit, and isolated install smoke pass |
| `init`, `scan`, `status`, `lint`, `note new/show/evolve`, `relation add/remove/list`, `migrate` | 1 | vault, parser, identity, atomicity, conflict, recovery, and migration tests |
| paper capture application service, `source list/show/open/sync`, `inbox`, `process` | 2A | canonical DOI/arXiv identity, loopback Zotero recovery, synchronization ownership/conflicts, primary-PDF integrity, explicit workflow transitions, and no public add command |
| `add`, `snippet add` | 2B | four-type recognition, override, add-result JSON, failure atomicity, snapshot, edition, commit/range, and license checks |
| `grep`, `search`, `index`, `get`, `context` | 3 | deterministic projection and result-to-file explanation |
| `serve` read views | 4 | shared-service parity and local-service security |
| `ai list/review/promote`, automation JSON, extended `doctor` adapter probes | 5 | promotion audit and explicit-scope tests |
| `related`, `backlinks`, `history`, `note merge/supersede`, `tidy`, `organize`, `review` | 6A | identity and history preservation |
| `publish audit/build/preview` | 6B | complete closure and adversarial staging tests |

This matrix is the only delivery-batch authority.

## Phase 2A executable gate

Phase 2A follows [`phase2a-goal.md`](phase2a-goal.md) and
[`ADR-0012`](decisions/0012-phase2a-paper-zotero-design.md). It is complete only when all of the
following are directly proven:

- DOI/arXiv normalization, version handling, alias matching, split-identity conflict, and repeated
  internal capture are deterministic;
- new Zotero-only items are ineligible for automated capture while existing readable v2 Sources are
  preserved;
- the read-only loopback Zotero adapter covers unavailable, timeout, permission, missing-item, and
  malformed-response failures without reading private SQLite;
- zero, one, and multiple PDF candidates, integrity match/mismatch, disposable cache, and explicit
  attachment replacement behave as specified without durable absolute paths;
- synchronization preserves human-owned fields, detects local managed-field edits and identifier
  collisions, adopts a safe first baseline, and uses expected-checksum atomic writes;
- Source list/show/open/sync, inbox, and explicit adjacent workflow transitions pass command-level
  tests, including versioned JSON where planned;
- SQLite remains unnecessary, public `kb add` remains unregistered, and the core wheel works without
  Zotero optional dependencies;
- the complete repository, type, lint, package audit, isolated-install, and supported-platform CI
  gates pass before any status is changed.

Phase 2B recognition, public `kb add`, Web/Book/OSS adapters, cloud Zotero access, multi-attachment
selection, and Phase 3 projection/search remain outside this gate.

## Deferred scope

Phase 7 includes vector/RAG implementation, MCP, graph databases/visualization, multi-agent memory, native readers/reference managers, browser extensions, and cloud synchronization. Full OSS clones, private attachment collections, generated public output, and direct AI modification of trusted facts are never default durable content.

## Acceptance dimensions

Contract changes require versioning and migration evidence. Durable identities survive rename and evolution. Facts resolve all Source/locator citations. AI promotion remains auditable. Search returns to durable segments. Public builds prove complete closure, isolation, and fail-closed behavior. Actual tests and CI results—not manually maintained test counts—are the status authority.
