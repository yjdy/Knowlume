# Interfaces: CLI and Web

> Status: Active  
> Baseline: v0.1  
> Authoritative for: user-facing commands, machine output, workflows, and management pages

All interfaces invoke application services; no domain rule is implemented independently in CLI or Web.

## CLI capability groups

| Group | Responsibility |
|---|---|
| Capture | add material and process inbox items |
| Organize | normalize structure and propose relationships |
| Inspect | show, search, traverse, and explain history |
| Maintain | validate contracts, environment, debt, and index health |
| Publish | audit, stage, preview, and build public material |

## Command surface

```text
kb init                         kb status
kb scan                         kb serve
kb add [paper|web|book|repo]    kb inbox
kb process SOURCE_ID            kb source [list|show|open|sync]
kb note [new|show|link|merge|supersede]
kb snippet add                  kb ai [list|review|promote]
kb grep QUERY                   kb search QUERY
kb get ID                       kb context QUERY
kb related ID                   kb backlinks ID
kb history ID                   kb tidy [--dry-run|--apply]
kb organize                     kb review
kb index [build|rebuild|status] kb lint [--strict|--changed]
kb doctor                       kb publish [audit|build|preview]
```

Implementation batches and phase ownership belong to [`roadmap.md`](roadmap.md).

## Capture

Explicit source types are accepted, while URL/identifier recognition may infer paper, web, book, or OSS. `--type` overrides inference.

| Input identity | Inferred source type |
|---|---|
| arXiv identifier/URL or DOI | `paper` |
| GitHub or GitLab repository URL | `oss` |
| ISBN | `book` |
| Other ordinary URL | `web` |

If an input matches more than one category or cannot be identified confidently, capture stops with a typed ambiguity diagnostic. It does not guess.

```text
normalize -> duplicate check -> metadata -> adapter sync
          -> source card(active/inbox) -> index
```

Repeated capture is idempotent for the same canonical identity. Ambiguous type or duplicate conflicts are reported instead of silently creating another source.

## Organize

`kb tidy` changes representation but not knowledge meaning. It defaults to dry-run and may normalize frontmatter ordering, tags, filenames, generated links, stale cache references, and update timestamps.

`kb organize` produces suggestions only: possible duplicates, missing synthesis, and candidate related/merge/supersede relations. V1 uses strings, tags, sources, and links rather than semantic search.

## Inspect

`kb status` reports object/source counts, visibility, workflow backlog, unreviewed AI, indexed objects, last index time, and health findings.

`get`, `source show`, `note show`, `backlinks`, `related`, and `history` preserve stable IDs in output so humans and automation can follow references across renames.

## Maintain

- `lint` validates schemas, IDs, references, stable sections, locators, AI review, snippet provenance, visibility dependencies, and projection consistency.
- Normal lint output grades findings as `ERROR`, `WARN`, or `INFO`. `ERROR` means a violated contract or unsafe state; `WARN` means accepted maintenance debt or incomplete provenance; `INFO` is advisory.
- `lint --strict` treats every `WARN` as an error for CI, pre-commit, and publishing. In v1, a missing locator for some private facts may be a warning, but public publishing applies the stricter policy.
- `lint --changed` limits file selection using Git but still checks affected references.
- `doctor` checks the runtime environment, not knowledge quality.
- `review` reports maintenance debt and never changes knowledge automatically. Its six v1 categories are:
  1. inbox sources left unprocessed for a configured period;
  2. processed sources without a literature note or synthesis;
  3. developing notes not updated for a configured period;
  4. potential duplicate concepts;
  5. unreviewed AI artifacts;
  6. public notes that reference a superseded note.

## Machine-readable output

Commands that support `--json` emit one versioned JSON document to stdout. Diagnostics go to stderr. The envelope includes contract version, command, success state, data, warnings, and typed errors. Exit codes distinguish usage, contract, external dependency, security/audit, and unexpected failures.

Human formatting is not parsed by automation. Backward-incompatible JSON changes require a contract version change.

## Web management interface

V1 uses FastAPI, Jinja2, and HTMX over the same application services as the CLI. Initial pages are:

1. Dashboard and Knowledge Health;
2. Sources;
3. Notes;
4. Search;
5. AI Review;
6. Publish.

The Sources page filters by source type, `record_status`, `workflow_stage`, tags, updated time, and linked notes. The Notes page filters by `note_type`, `maturity`, `visibility`, `record_status`, and source. Search presents the shared FTS results with segment previews. AI Review supports inspecting, accepting, rejecting, and promoting AI artifacts. Publish shows public objects, readiness, failed audit findings, and the preview entry point.

The first Web slice is read-only. Mutating actions are added only after atomic writes, conflict detection, CSRF protection, and audit behavior exist.

Knowledge Health includes sources without notes, notes without sources, facts without locators, broken links, unreviewed AI, public-to-private dependencies, unindexed sources, and stale index entries.

## Local service boundary

`kb serve` binds to loopback by default. Network exposure, authentication, and remote access are outside v1 unless explicitly configured. Rendering untrusted Markdown must prevent script injection; file/open actions must prevent path traversal and shell injection.
