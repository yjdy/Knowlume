# Interfaces: CLI and Web

> Status: Active — Contract v2
> Authoritative for: user-facing commands, machine output, vault discovery, and management surfaces

All interfaces call shared application services. Phase 0R defines these contracts only; it does not provide an executable `kb` package, CLI, migration tool, or Web service.

## Command surface and ownership

```text
kb init PATH
kb status                         kb scan
kb add INPUT [--type paper|web|book|repo] [--json]
kb source [list|show|open|sync]
kb inbox                          kb process SOURCE_ID
kb note new --type idea|literature|concept|synthesis
kb note show ID                   kb note evolve ID --to concept
kb relation [add|remove|list]     kb snippet add
kb grep QUERY                     kb search QUERY
kb get ID                         kb context QUERY
kb related ID                     kb backlinks ID
kb history ID
kb note merge SOURCE_ID --into TARGET_ID
kb note supersede OLD_ID --by NEW_ID
kb tidy [--dry-run|--apply]       kb organize
kb review
kb index [build|rebuild|status]   kb lint [--strict|--changed]
kb ai [list|review|promote]       kb publish [audit|build|preview]
kb migrate --from 1 --to 2 [--dry-run|--apply]
kb doctor                         kb serve
```

The unique command-to-phase-to-gate matrix is maintained in the [roadmap](roadmap.md).

## Vault discovery

`--vault PATH` is a global option and precedes the subcommand, for example
`kb --vault PATH scan`. Resolution stops at the first present source in this order:

1. `--vault PATH`;
2. `KNOWLUME_VAULT`;
3. search upward from the current directory for `knowlume.toml`;
4. the platformdirs user data location `knowlume/vault`.

`kb init PATH` uses its positional path and does not run discovery. If global `--vault` is also
present, both normalized paths must identify the same target. Repeated explicit values that normalize
to different targets are ambiguous. Once a source is selected, lower-priority sources are not
consulted; this makes an intentional explicit override deterministic.

The selected root must contain one valid [`knowlume.toml`](../schemas/config/README.md), except while
`init` is creating it. Missing markers, invalid configuration, unsupported versions, path escape, and
selection conflicts fail closed. The complete path, lock, and transaction rules are fixed by
[`ADR-0011`](decisions/0011-phase1-vault-and-transaction-contracts.md). A configured vault is
independent from the program repository.

### Phase 1 diagnostics

These codes and exit classes are stable. Commands may add contextual `object_id`, safe relative
`path`, or `details`, but must not expose note bodies, credentials, or unnecessary absolute vault
paths.

| Code | Exit | Meaning |
|---|---:|---|
| `VAULT_REQUIRED` | 3 | no vault was selected and no valid default marker exists |
| `VAULT_NOT_FOUND` | 3 | the selected root or its marker does not exist |
| `VAULT_CONFIG_INVALID` | 3 | TOML, schema, path uniqueness, or containment is invalid |
| `VAULT_CONFIG_UNSUPPORTED` | 3 | configuration or object Contract version is outside the readable range |
| `VAULT_AMBIGUOUS` | 3 | one discovery source supplies distinct normalized candidates |
| `VAULT_SELECTION_CONFLICT` | 3 | `kb init PATH` conflicts with global `--vault` |
| `VAULT_TARGET_NOT_EMPTY` | 3 | initialization target is non-empty and is not the same initialized vault |
| `VAULT_PATH_UNSAFE` | 6 | traversal, symlink, junction, or resolved containment escapes the vault |
| `VAULT_UNAVAILABLE` | 5 | filesystem permissions or availability prevent the requested access |
| `WRITE_CONFLICT` | 4 | a target differs from the expected checksum or existence state |
| `VAULT_LOCKED` | 4 | another writer or unrecovered lock owns the vault write lock |
| `TRANSACTION_RECOVERY_REQUIRED` | 4 | a valid interrupted transaction must be resumed or rolled back before writing |
| `TRANSACTION_MANIFEST_INVALID` | 3 | transaction state is malformed, unsupported, or inconsistent |
| `TRANSACTION_RECOVERY_CONFLICT` | 4 | neither forward recovery nor rollback is provably safe |

## Capture and mutation behavior

The only public capture surface is `kb add INPUT [--type paper|web|book|repo] [--json]`. It is released in Phase 2B only after all four capture paths pass their gates. Phase 2A delivers the internal paper/Zotero capture service without exposing a partial parent command. CLI type `repo` maps to durable `source_type: oss`.

Recognition is non-interactive and follows this order:

1. an explicit `--type` override;
2. arXiv identifier or URL -> paper;
3. DOI -> paper or book according to resolved metadata;
4. checksum-valid ISBN -> book;
5. repository URL on a known or configured Git host -> repo;
6. another HTTP(S) URL -> web.

Unavailable or ambiguous DOI metadata requires `--type`; it is never guessed. Unknown self-hosted Git URLs default to web unless the host is configured. An explicit `--type repo` still requires adapter-backed resolution of a canonical project root. Local files, clipboard bodies, and batch input are outside the first command contract.

The capture flow is `normalize -> recognize -> metadata resolve -> canonical identity -> duplicate check -> Source construction -> adapter snapshot/sync -> atomic write -> scan`. Once the Phase 3 projection exists, a successful capture also requests an index refresh, but index availability is never a Phase 2B write prerequisite. `--type` does not bypass metadata, canonicalization, schema, snapshot, license, or safety checks. Any ambiguity or failure leaves no Source card, relation, or partial update. Repeated capture of the same canonical identity succeeds with the existing Source ID and `created: false`.

Note evolution from Idea to Concept preserves the Note and section IDs and appends `type_history`. Relation operations write only the shard owned by the source object. Migration defaults to dry-run and refuses apply while required decisions or blocking findings remain.

## Machine interface v1

Commands that support JSON emit exactly one document matching the [CLI envelope v1 schema](../schemas/interfaces/cli-envelope-v1.schema.json) to stdout; diagnostics go to stderr. `interface_version` is independent from object, locator, relation, projection, and parser/tokenizer versions.

Successful `kb add --json` data matches the [add result v1 schema](../schemas/interfaces/add-result-v1.schema.json). `requested_type` records the explicit override or `null`; `detected_type` is the effective CLI type after applying that override. The result always records the corresponding durable `source_type`, canonical identity, Source ID, and whether a new Source was created.

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

The principal `kb add` diagnostics are fixed as:

| Code | Exit | Meaning |
|---|---:|---|
| `ADD_INPUT_INVALID` | 2 | input has no accepted identifier or URL shape |
| `ADD_TYPE_AMBIGUOUS` | 3 | source type cannot be selected without `--type` |
| `ADD_METADATA_UNAVAILABLE` | 5 | required metadata or capture adapter is unavailable |
| `ADD_WRITE_CONFLICT` | 4 | durable state changed before the atomic write |

The [migration report v1 schema](../schemas/interfaces/migration-report-v1.schema.json) distinguishes automatic changes, required human decisions, blocking findings, and prohibited inference.

## Web management interface

The first Web slice is read-only and follows the search projection. Dashboard, Sources, Notes, Search, and Knowledge Health views derive from the same services as CLI. Mutations wait for atomic writes, conflict detection, CSRF protection, and audit behavior.

The local service binds to loopback by default and validates Host and Origin. It does not enable permissive CORS. Markdown is sanitized, responses use security headers, and file operations enforce configured path boundaries.
