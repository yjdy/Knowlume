# ADR-0011: Freeze Phase 1 Vault and transaction contracts

- Status: Accepted
- Date: 2026-08-27
- Decision owners: Knowlume maintainers

## Context

Phase 1 introduces the first commands that discover and mutate an independent Vault. The existing
architecture fixes the discovery order and requires conflict-aware single-file writes plus
recoverable multi-file transactions, but it does not yet freeze the portable configuration shape,
transaction state machine, CLI option placement, or typed Vault failures.

## Decision

### Portable Vault configuration

`knowlume.toml` follows configuration contract v1, whose executable schema is
[`../../schemas/config/v1/knowlume.schema.json`](../../schemas/config/v1/knowlume.schema.json).
It records `config_version = 1`, `object_contract_version = 2`, and the relative directories for
Sources, Notes, Snippets, AI Artifacts, relations, and disposable state. Paths use portable POSIX
relative syntax, cannot contain `..`, and must resolve inside the Vault. Configured durable roots
and the state root must be distinct and non-overlapping.

The file contains no machine-specific absolute path, credential, adapter endpoint, lock, or
transaction record. A future incompatible configuration change increments `config_version`
independently from object, locator, relation, interface, projection, parser, and transaction
versions.

### CLI placement and discovery

`--vault PATH` is a root option and therefore precedes the command: `kb --vault PATH scan`.
`kb init PATH` owns its explicit target and does not perform discovery. Supplying root `--vault`
with `init PATH` is a usage conflict even if the paths appear equal.

Other Vault commands resolve exactly one candidate in this order: root `--vault`,
`KNOWLUME_VAULT`, the nearest ancestor containing `knowlume.toml`, then the platformdirs default
`user_data_dir("knowlume")/vault`. A higher-priority candidate replaces lower-priority candidates;
lower-priority candidates do not create ambiguity. Each selected candidate is canonicalized before
validation. Aliases that resolve inconsistently, multiple same-precedence candidates supplied by a
future configuration source, or overlapping configured roots fail as ambiguous or conflicting.
No missing candidate is created implicitly.

Phase 1 Vault diagnostics are stable:

| Code | Exit | Meaning |
|---|---:|---|
| `VAULT_ARGUMENT_CONFLICT` | 2 | `--vault` is combined with `init PATH`, or mutually exclusive options are combined |
| `VAULT_NOT_FOUND` | 3 | no selected candidate or marker exists |
| `VAULT_INVALID` | 3 | marker, topology, path, or configuration content is invalid |
| `VAULT_VERSION_UNSUPPORTED` | 3 | configuration or object Contract is newer or otherwise unreadable |
| `VAULT_PATH_CONFLICT` | 3 | configured roots overlap or contradict the selected root |
| `VAULT_AMBIGUOUS` | 3 | one precedence level resolves to more than one Vault |
| `VAULT_WRITE_CONFLICT` | 4 | durable content changed after it was read |
| `VAULT_LOCKED` | 4 | another writer owns the Vault lock |
| `VAULT_RECOVERY_REQUIRED` | 4 | an unfinished transaction must be recovered before a new write |
| `VAULT_RECOVERY_FAILED` | 4 | safe deterministic recovery could not be completed |
| `VAULT_PATH_UNSAFE` | 6 | traversal, link, junction, or resolved-path escape crosses the Vault boundary |

Human-readable Phase 1 commands do not gain an implicit `--json` option. `migrate` emits the
already-versioned migration report v1. Scanner and lint services use
[`finding-v1`](../../schemas/interfaces/finding-v1.schema.json); a later public JSON option must use
the CLI envelope and receive its own result schema before release.

### Transaction protocol

Transaction contract v1 is defined by
[`transaction-manifest.schema.json`](../../schemas/transactions/v1/transaction-manifest.schema.json).
One exclusive lock exists at `.knowlume/locks/vault-write.lock`. A transaction owns
`.knowlume/transactions/<transaction_id>/`, containing an atomically replaced `manifest.json`,
same-filesystem staged replacements, and backups. Manifest paths are Vault-relative and must remain
inside the resolved Vault after link-aware canonicalization.

Before the first durable replacement, the writer validates every expected checksum and persists a
`prepared` manifest. Entries commit in manifest order. Manifest and entry state are persisted before
and after each replace so interruption is observable. The transaction states are `preparing`,
`prepared`, `committing`, `rolling_back`, `committed`, and `rolled_back`; entry states are `pending`,
`backed_up`, `replaced`, and `restored`.

Recovery is fail-closed and idempotent:

- `preparing` or `prepared`: restore any recorded backup and roll back;
- `committing`: roll back every replaced entry in reverse order;
- `rolling_back`: continue rollback in reverse order;
- `committed`: verify committed checksums, then clean disposable transaction state;
- `rolled_back`: verify original checksums, then clean disposable transaction state.

An unsupported manifest version, malformed lock, unexplained transaction directory, checksum
mismatch, or path outside the Vault stops recovery. No new write begins while recovery is required.
Cleanup removes only the validated transaction directory and releases only the lock owned by that
transaction.

## Migration impact

Contract v2 object files do not change, and Contract v1 remains byte-stable. Existing directories
without `knowlume.toml` are not silently adopted; `kb init` or an explicit migration workflow is
required. Configuration v1 has no predecessor. Transaction state is disposable and is never
migrated; unsupported manifests require compatible recovery tooling or manual operator review.

## Consequences

- Installed and source-checkout commands share one deterministic discovery and failure model.
- Portable configuration can be copied with a Vault without leaking machine state.
- Crash recovery has a finite, testable state machine and never reports partial success.
- Future JSON surfaces, configuration revisions, and transaction revisions require explicit version
  decisions rather than inheriting Contract v2 implicitly.
