# ADR-0011: Freeze Phase 1 vault discovery and transaction recovery contracts

- Status: Accepted
- Date: 2026-08-27
- Decision owners: Knowlume maintainers

## Context

ADR-0006 requires an independent portable vault, conflict-aware single-file writes, and recoverable
multi-file writes. Phase 1 cannot implement those behaviors safely until configuration identity,
discovery conflicts, lock ownership, transaction progress, and recovery outcomes are machine-readable
and independently versioned.

## Decision

### Portable vault configuration

A vault root contains `knowlume.toml` conforming to
[`knowlume.schema.json`](../../schemas/config/v1/knowlume.schema.json). Configuration version 1
contains a stable `vault_id`, writable object Contract version 2, and relative POSIX paths for the five
durable collections. Configured paths are pairwise distinct, non-overlapping after lexical
normalization, and contained by the resolved vault root after filesystem resolution. The fixed
machine-local state directory is `.knowlume`; it is not configurable.

`kb init PATH` uses its positional path and never performs ordinary vault discovery. A global
`--vault PATH` may accompany `init` only when both paths resolve to the same target; otherwise the
command fails with `VAULT_SELECTION_CONFLICT`. For every other vault command, `--vault` is a global
option written before the subcommand and resolution stops at the first present source:

1. `--vault PATH`;
2. `KNOWLUME_VAULT`;
3. the nearest ancestor containing `knowlume.toml`;
4. the platformdirs user data location `knowlume/vault`.

A repeated explicit option with different normalized values is ambiguous. A selected path must
contain exactly one valid marker and supported configuration/object versions. Lower-priority sources
are not consulted after a source is selected, so an intentional explicit override is deterministic.
Path containment is checked after resolving existing ancestors; traversal and symlink or junction
escape fail closed.

### Single-writer lock

All multi-file operations acquire `.knowlume/locks/vault-write.json` by exclusive creation. The lock
conforms to [`vault-write-lock.schema.json`](../../schemas/state/v1/vault-write-lock.schema.json) and
contains an opaque owner token. A writer removes only a lock with its own token. A leftover lock is
never broken merely because its process ID appears inactive; the associated manifest must first be
validated and explicitly recovered or rolled back.

### Transaction manifest and state machine

Each operation stores
`.knowlume/transactions/<transaction_id>/manifest.json` conforming to
[`transaction-manifest.schema.json`](../../schemas/state/v1/transaction-manifest.schema.json). Every
manifest records the intended outcome and the expected, staged, backup, and current state of each
target. Manifest updates themselves use checksum-aware atomic replacement.

The forward state sequence is:

```text
locked -> staging -> staged -> committing -> committed -> cleaning -> complete
```

Any non-terminal state may enter rollback:

```text
locked|staging|staged|committing|committed -> rolling_back -> rolled_back -> cleaning -> complete
```

Before a target replacement, the writer verifies `expected_checksum`, materializes and verifies any
backup, records `backed_up`, then atomically replaces or deletes the target and records `applied`.
Rollback restores verified backups or removes targets whose `original_exists` is false, then records
`restored`. `outcome` is `pending` until commit or rollback is chosen, `commit` after the durable set
is complete, and `rollback` once rollback begins. Cleanup removes only recorded staging and backup
paths after the durable outcome is verified.

Recovery validates the schema, vault ID, transaction ID/path agreement, checksums, unique targets,
state/outcome combination, and every target's observable bytes. A matching retry may resume a
provably safe commit. If forward recovery cannot be proven and every required backup is valid, the
transaction rolls back. If neither action is provably safe, no durable file is changed and
`TRANSACTION_RECOVERY_CONFLICT` is returned. Read-only commands may report pending recovery but do
not alter it.

### Stable Phase 1 diagnostics

The names and exit classes of vault, path, write, lock, and recovery diagnostics are owned by
[`interfaces.md`](../interfaces.md). Human output writes diagnostics to stderr. A command that later
adds JSON output must use CLI envelope v1; no unversioned Phase 1 JSON result is permitted.

## Consequences

- Configuration and transaction formats can evolve independently of Contract v2.
- A copied vault retains its identity; discovery still selects a concrete root and never merges two
  copies implicitly.
- Crash recovery costs additional fsyncs and manifest writes, but every mutation boundary is
  inspectable.
- Platform-specific locking and replacement adapters must produce the same typed observable outcomes.
- Transaction state is disposable after verified completion and is never the only source of a
  knowledge fact.

## Migration impact

This decision introduces configuration v1 and transaction v1 before Phase 1 production vaults exist,
so no existing production durable file requires migration. Contract v1 knowledge fixtures remain
read-only migration input. Any future incompatible configuration or transaction record requires its
own version decision and explicit handling; package install or upgrade never performs it.

## Alternatives considered

- Reuse object `schema_version` for configuration and transactions: rejected because their lifecycles
  and compatibility ranges are independent.
- Infer progress from target, temporary, or backup file presence: rejected because a crash can occur
  between any filesystem operation and the next observation.
- Automatically break a lock from PID liveness alone: rejected because PID reuse and platform
  differences can admit concurrent writers.

