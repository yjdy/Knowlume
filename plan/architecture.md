# Architecture

> Status: Active  
> Baseline: v0.1  
> Authoritative for: system boundaries, dependency direction, logical layers, and repository layout

## Purpose

Knowlume is a local-first Knowledge Operating System for long-term learning and knowledge evolution. It preserves traceable sources, connects human notes to evidence, exposes a stable `kb` control plane to humans and automation, and promotes reviewed private knowledge into explicitly public material.

The architectural center is deliberately small:

```text
Markdown/YAML + stable external source references
                    |
                    v
               kb-core (Python)
          +---------+---------+
          |         |         |
          v         v         v
        CLI       Web UI   Index projection
          |                   SQLite FTS5
          v
   Codex / other harnesses
```

Obsidian, Zotero, Git, Quartz, and future native components are replaceable adapters. None of them owns the domain model.

## Architectural invariants

1. Tracked Markdown/YAML and stable references to original material are the durable knowledge source.
2. SQLite, caches, derived content, and public staging are rebuildable or disposable.
3. CLI, Web, and automation invoke the same application services.
4. Domain code depends on ports, never directly on Zotero, Obsidian, Quartz, GitHub, or UI frameworks.
5. New knowledge is private by default; public output is built from an allowlist into a separate staging tree.
6. Reliability precedes semantic search, RAG, MCP, graphs, and multi-agent features.

Detailed object rules live in [`data-model.md`](data-model.md). Persistence and search mechanics live in [`storage-index-search.md`](storage-index-search.md). Security enforcement lives in [`security-publishing.md`](security-publishing.md).

## Logical layers

| Layer | Responsibility | May depend on |
|---|---|---|
| `domain` | Source, Note, Snippet, AI Artifact, Relation, provenance, stable value types | Python standard library and domain-local code |
| `application` | capture, process, scan, search, index, lint, review, publish use cases | domain and ports |
| `ports` | storage, reference manager, search, version control, publishing, repository access contracts | domain contracts |
| `adapters` | Filesystem, Zotero, Obsidian, Git, Quartz, GitHub implementations | ports plus external libraries |
| `cli` | Typer commands and machine-readable output | application services |
| `web` | FastAPI/Jinja2/HTMX management interface | application services |

Dependency direction points inward. Adapters and interfaces may be replaced without migrating durable knowledge files.

## Repository layout

```text
Knowlume/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── schemas/                    # executable contracts
├── templates/                  # object creation templates
├── plan/                       # active design and roadmap
├── src/kb/
│   ├── domain/
│   ├── application/
│   ├── ports/
│   ├── adapters/
│   ├── index/
│   ├── cli/
│   └── web/
├── knowledge/
│   ├── sources/{papers,web,books,oss}/
│   ├── notes/{literature,concept,synthesis,evergreen}/
│   ├── snippets/
│   └── ai/{artifacts,tmp}/
├── migrations/
├── tests/
├── .cache/                     # ignored
├── derived/                    # ignored
├── public-staging/             # ignored, generated
└── kb.sqlite                   # ignored, rebuildable
```

Large PDF/EPUB files, Zotero storage, logs, temporary clones, and generated output do not enter Git by default. Source-specific preservation rules are defined in [`sources-and-adapters.md`](sources-and-adapters.md).

## Principal flows

### Capture

```text
CLI/Web -> application capture use case -> reference adapter
        -> source card in file store -> scanner -> index projection
```

The detailed command and error contract belongs to [`interfaces.md`](interfaces.md).

### Search and context

```text
CLI/Web/Codex -> SearchBackend port -> file or FTS implementation
              -> visibility/AI filters -> typed result or JSON output
```

Search ranking and index behavior belong to [`storage-index-search.md`](storage-index-search.md).

### Publish

```text
explicit allowlist -> transitive audit -> isolated public-staging
                   -> Quartz adapter -> preview/build output
```

The private/public trust boundary belongs to [`security-publishing.md`](security-publishing.md).

## External boundaries

- Zotero owns reference-manager records and attachments, accessed through a supported local API.
- Obsidian is a Markdown editor, not a database.
- Git records tracked knowledge and code evolution, not disposable projections.
- Quartz receives only audited public staging.
- External LLM access is absent from v1; any future integration requires an explicit data-release policy.

## Evolution rule

Architecture changes that alter durable files, IDs, visibility, relations, locators, or publish boundaries require a versioned contract change. Update schemas, templates, fixtures, tests, and the relevant ADR before implementation.
