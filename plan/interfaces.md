# Interfaces: CLI and Web

> Status: Active — Contract v2
> Authoritative for: user-facing commands, machine output, vault discovery, and management surfaces

All interfaces call shared application services. Phase 0R defines these contracts only; it does not provide an executable `kb` package, CLI, migration tool, or Web service.

## Command surface and ownership

```text
kb init PATH
kb status                         kb scan
kb add [paper|web|book|repo]      kb source [list|show|open|sync]
kb note new --type idea|literature|concept|synthesis
kb note show ID                   kb note evolve ID --to concept
kb relation [add|remove|list]     kb snippet add
kb grep QUERY                     kb search QUERY
kb get ID                         kb context QUERY
kb index [build|rebuild|status]   kb lint [--strict|--changed]
kb ai [list|review|promote]       kb publish [audit|build|preview]
kb migrate --from 1 --to 2 [--dry-run|--apply]
kb doctor                         kb serve
```

The unique command-to-phase-to-gate matrix is maintained in the [roadmap](roadmap.md).

## Vault discovery

Resolution order is:

1. `--vault PATH`;
2. `KNOWLUME_VAULT`;
3. search upward from the current directory for `knowlume.toml`;
4. user-level default vault.

Multiple candidates or conflicting configuration produce a typed ambiguity error. A configured vault is independent from the program repository.

## Capture and mutation behavior

DOI/arXiv, GitHub/GitLab URLs, ISBN, and ordinary URLs may infer paper, OSS, book, and web sources respectively. An explicit type overrides inference. Ambiguous identity stops rather than guessing, and repeated capture of the same canonical identity is idempotent.

Note evolution from Idea to Concept preserves the Note and section IDs and appends `type_history`. Relation operations write only the shard owned by the source object. Migration defaults to dry-run and refuses apply while required decisions or blocking findings remain.

## Machine interface v1

Commands that support JSON emit exactly one document matching the [CLI envelope v1 schema](../schemas/interfaces/cli-envelope-v1.schema.json) to stdout; diagnostics go to stderr. `interface_version` is independent from object, locator, relation, projection, and parser/tokenizer versions.

Exit codes are frozen as:

| Code | Meaning |
|---:|---|
| 0 | success |
| 1 | unexpected internal failure |
| 2 | argument or usage error |
| 3 | contract, parse, or reference error |
| 4 | concurrent modification conflict |
| 5 | external dependency unavailable |
| 6 | security or publish-audit failure |

The [migration report v1 schema](../schemas/interfaces/migration-report-v1.schema.json) distinguishes automatic changes, required human decisions, blocking findings, and prohibited inference.

## Web management interface

The first Web slice is read-only and follows the search projection. Dashboard, Sources, Notes, Search, and Knowledge Health views derive from the same services as CLI. Mutations wait for atomic writes, conflict detection, CSRF protection, and audit behavior.

The local service binds to loopback by default and validates Host and Origin. It does not enable permissive CORS. Markdown is sanitized, responses use security headers, and file operations enforce configured path boundaries.
