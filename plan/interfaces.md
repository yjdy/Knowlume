# Interfaces: CLI and Web

> Status: Active — Contract v2
> Authoritative for: user-facing commands, machine output, vault discovery, and management surfaces

All interfaces call shared application services. Phase 1 Vault, scanner, Note, relation, and explicit
v1-to-v2 migration commands are implemented; the Web service remains unimplemented.

## Command surface and ownership

```text
kb --version
kb [--vault PATH] COMMAND
kb doctor [--json]
kb update-check [--pre] [--json]
kb init PATH
kb status                         kb scan
kb add INPUT [--type paper|web|book|repo] [--json]
kb source [list|show|open|sync]
kb inbox                          kb process SOURCE_ID
kb note new --type idea|literature|concept|synthesis [--source SOURCE_ID]
kb note show ID                   kb note evolve ID --to concept
kb relation add FROM_ID TO_ID --type TYPE [--section SECTION_ID]
kb relation remove FROM_ID TO_ID --type TYPE [--section SECTION_ID]
kb relation list ID              kb snippet add
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

Resolution order is:

1. `--vault PATH`;
2. `KNOWLUME_VAULT`;
3. search upward from the current directory for `knowlume.toml`;
4. user-level default vault.

Multiple candidates or conflicting configuration produce a typed ambiguity error. A configured vault is independent from the program repository.

`--vault` is a root option and precedes the command. `kb init PATH` uses only its positional target;
combining it with root `--vault` is `VAULT_ARGUMENT_CONFLICT` (exit 2). Other Vault commands do not
implicitly create a missing candidate. Configuration, discovery, conflict, recovery, and unsafe-path
diagnostics are frozen by [ADR-0011](decisions/0011-phase1-vault-and-transaction-contracts.md).

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

### Phase 2A Source interface

The implemented Phase 2A syntax is:

```text
kb source list [--type TYPE] [--stage STAGE] [--status STATUS] [--visibility VISIBILITY] [--json]
kb source show ID [--json]
kb source open ID
kb source sync ID [--adopt-remote] [--accept-attachment-change] [--json]
kb inbox [--json]
kb process ID --to reading|processed|integrated [--json]
```

These options are registered and covered by command-level tests. Their delivery status and
verification evidence are synchronized in [`CLI.md`](../CLI.md).

`source list` and `inbox` scan durable files and do not depend on SQLite. Source list sorts by
`updated` descending then Source ID ascending. Inbox lists `workflow_stage=inbox` Sources by
`created` ascending then Source ID ascending. `source show` resolves a stable Source ID and displays
normalized metadata and recovery information without probing or mutating the adapter.

`source open` is human-facing and has no JSON mode. It resolves the recorded primary PDF through the
Zotero adapter into disposable cache, verifies its integrity when known, and asks the operating
system to open it. Missing capability or material uses exit code 5; a known content-hash mismatch is
a conflict and does not open unverified bytes.

`source sync` updates Zotero-owned metadata automatically only when the durable synchronization
baseline, external identity, attachment integrity, and expected file checksum are safe. A no-op is
successful and byte-preserving. `--adopt-remote` is reserved for a pre-existing Source without a
matching baseline; `--accept-attachment-change` explicitly accepts replacement PDF bytes and warns
that existing Fact locators need review. Failures produce no partial write.

`process` requires an explicit adjacent target in
`inbox -> reading -> processed -> integrated`. Requesting the current stage succeeds without a
rewrite. A skipped, backward, or post-integrated transition is a contract error.

Note evolution from Idea to Concept preserves the Note and section IDs and appends `type_history`. Relation operations write only the shard owned by the source object. Migration defaults to dry-run and refuses apply while required decisions or blocking findings remain.

Relation `--section` identifies a stable section on the stored target. `related_to` is stored once in
canonical object-ID order, and incoming navigation is derived by scanning rather than persisted as a
backlink. Add and remove compare the complete canonical key; omitting `--section` cannot remove a
section-targeted relation.

`note new --type literature` requires `--source SOURCE_ID` and atomically creates the required
`summarizes` relation. `--source` is rejected for the other Note types; no Source is guessed.

## Machine interface v1

CLI stdout and stderr use UTF-8 on every supported platform. Commands that support JSON emit exactly one document matching the [CLI envelope v1 schema](../schemas/interfaces/cli-envelope-v1.schema.json) to stdout; diagnostics go to stderr. `interface_version` is independent from object, locator, relation, projection, and parser/tokenizer versions.

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

Phase 1 scanner and lint services use the versioned
[`finding-v1`](../schemas/interfaces/finding-v1.schema.json) shape. Phase 1 commands remain
human-readable unless their syntax explicitly includes `--json`; `migrate` emits migration-report
v1. Any later JSON option requires an explicit result schema inside CLI envelope v1 before release.

Phase 2A JSON options use explicit interface schemas for Source list, Source show, Source
synchronization, and Source workflow results. Inbox reuses the Source-list result with an explicit
inbox filter. `source open` remains human-facing and has no JSON schema.

The schema filenames are:

- `source-list-result-v1.schema.json` for `source list` and `inbox`;
- `source-show-result-v1.schema.json` for `source show`;
- `source-sync-result-v1.schema.json` for `source sync`;
- `source-workflow-result-v1.schema.json` for `process`.

Phase 2A uses these typed diagnostics:

| Code | Exit/severity | Meaning |
|---|---:|---|
| `PAPER_CANONICAL_IDENTITY_MISSING` | 3 | resolved Paper metadata has neither DOI nor arXiv identity |
| `PAPER_IDENTITY_CONFLICT` | 3 | canonical identifiers resolve to different Sources or an existing identity changes |
| `PAPER_ATTACHMENT_UNAVAILABLE` | warning | capture/sync found no readable primary PDF |
| `PAPER_ATTACHMENT_AMBIGUOUS` | warning | capture/sync found more than one primary-PDF candidate and selected none |
| `PAPER_ATTACHMENT_CHANGED` | 4 | recovered bytes do not match the durable attachment hash |
| `SOURCE_SYNC_LOCAL_MODIFIED` | 4 | current adapter-managed fields do not match their durable baseline |
| `SOURCE_SYNC_BASELINE_REQUIRED` | 4 | a legacy Source differs from Zotero and requires explicit remote adoption |
| `SOURCE_WORKFLOW_INVALID` | 3 | requested Source stage skips, regresses, or advances beyond the workflow |
| `ZOTERO_CAPABILITY_UNAVAILABLE` | 5 | the optional `knowlume[zotero]` transport dependency is not installed |
| `ZOTERO_API_UNAVAILABLE` | 5 | the Zotero Local API is disabled, unreachable, or returned an unexpected failure |
| `ZOTERO_ITEM_UNAVAILABLE` | 5 | the recorded Zotero item or requested attachment cannot be recovered |

Expected-checksum failures continue to use the Phase 1 `VAULT_WRITE_CONFLICT` diagnostic rather
than introducing a Source-specific duplicate.

`kb --version` reports package and independent contract/projection/parser versions without resolving a vault. `kb doctor` currently validates the Python runtime and bundled release assets; later phases extend it with vault and adapter capability probes without changing its command identity.

`kb update-check` is the only package-update network operation. It runs only when invoked, never installs an update, defaults to stable versions, and uses `--pre` to consider prereleases. JSON success data follows [update-check result v1](../schemas/interfaces/update-check-result-v1.schema.json). Unavailable or malformed package metadata emits `UPDATE_CHECK_UNAVAILABLE` with exit code 5. No vault path, object identity, content, or usage data is sent.

## Web management interface

The first Web slice is read-only and follows the search projection. Dashboard, Sources, Notes, Search, and Knowledge Health views derive from the same services as CLI. Mutations wait for atomic writes, conflict detection, CSRF protection, and audit behavior.

The local service binds to loopback by default and validates Host and Origin. It does not enable permissive CORS. Markdown is sanitized, responses use security headers, and file operations enforce configured path boundaries.
