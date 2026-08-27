# Machine-local state contracts

State versions are independent from configuration and durable object contracts. These files are
recoverable machine-local evidence, not durable knowledge and not a source of business facts.

- [`v1/vault-write-lock.schema.json`](v1/vault-write-lock.schema.json) defines the single-writer lock
  record stored at `.knowlume/locks/vault-write.json`.
- [`v1/transaction-manifest.schema.json`](v1/transaction-manifest.schema.json) defines the manifest
  stored below `.knowlume/transactions/<transaction_id>/manifest.json`.

The state machine and recovery rules are fixed by
[`ADR-0011`](../../plan/decisions/0011-phase1-vault-and-transaction-contracts.md). Manifests record a
global state, intended outcome, and per-target state so recovery never infers progress from missing
temporary files or timestamps.

