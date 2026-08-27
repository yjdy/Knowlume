# Architecture

> Status: Active  
> Baseline: Contract v2
> Authoritative for: system boundaries, dependency direction, logical layers, and vault topology

## Purpose and invariants

Knowlume is a local-first Knowledge Operating System for long-term learning and knowledge evolution. It keeps sourced Facts, source-free human thought, reviewed AI material, and public output distinguishable.

1. Tracked Markdown/YAML and stable external references are durable knowledge.
2. SQLite, caches, transaction state, derived output, and public staging are rebuildable.
3. Application code and personal vaults are separate.
4. CLI, Web, and automation invoke the same application services.
5. Domain code depends on ports, not Zotero, Obsidian, Git, Quartz, or UI frameworks.
6. New objects are private by default; public output is built from an audited allowlist.
7. Reliability and provenance precede semantic search, MCP, graphs, and multi-agent features.

## Logical layers

| Layer | Responsibility | May depend on |
|---|---|---|
| `domain` | immutable objects, sections, citations, relations, provenance values | standard library and domain-local code |
| `application` | init, capture, scan, lint, search, review, migration, publish | domain and ports |
| `ports` | vault, file store, reference manager, search, VCS, publisher contracts | domain contracts |
| `adapters` | filesystem, Zotero, Obsidian, Git, Quartz implementations | ports and external libraries |
| `cli` / `web` | human and machine interfaces | application services |

Dependencies point inward. Adapter replacement never requires a durable knowledge migration unless the versioned domain contract changes.

## Code and vault separation

The application repository contains code, schemas, templates, migrations, tests, and design documents. A personal vault is initialized independently:

```text
vault/
├── knowlume.toml
├── sources/{papers,web,books,oss}/
├── notes/{ideas,literature,concepts,syntheses}/
├── snippets/
├── ai/artifacts/
├── relations/
└── .knowlume/{locks,transactions}/   # ignored, disposable
```

`knowlume.toml` contains portable relative configuration. Absolute vault paths, credentials, adapter endpoints, locks, and transaction state are machine-local. Vault resolution is `--vault`, `KNOWLUME_VAULT`, nearest ancestor marker, then user default; ambiguity fails.

Application `private` visibility is not encryption and does not prevent Git pushes. Knowlume never performs Git commit, push, pull, or history rewriting implicitly.

## Principal flows

```text
capture/write -> application service -> conflict-aware vault port
              -> durable v2 file(s) -> scanner -> optional projection

query -> file or FTS SearchBackend -> provenance/visibility filters
      -> typed result -> CLI/Web/automation

public allowlist -> dependency classification -> audit
                 -> atomic isolated staging -> Quartz adapter
```

Single-file writes use expected checksums and same-directory atomic replacement. Multi-file use cases use a vault lock, transaction manifest, same-filesystem staging, and recovery. Windows and Linux expose the same conflict behavior; implementation begins in Phase 1.

## External boundaries

- Zotero owns reference-manager records and attachments, accessed only through supported APIs.
- Obsidian edits Markdown but owns no domain state.
- Git records durable-file evolution but is not a secrecy boundary.
- Quartz receives audited staging, never the private vault.
- External model access requires explicit caller scope and release policy.

Architecture changes affecting durable files, IDs, roles, visibility, locators, relations, or publishing require a new contract version and migration decision.
