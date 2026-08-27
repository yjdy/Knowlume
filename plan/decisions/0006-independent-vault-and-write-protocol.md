# ADR-0006: Code and knowledge use independent vaults

- Status: Accepted
- Date: 2026-08-26
- Decision owners: Knowlume maintainers

## Context

Application visibility is not filesystem encryption or Git remote protection. Keeping private knowledge inside the application source repository would make accidental publication and independent upgrades harder to control.

## Decision

Knowlume code and personal knowledge are separate. A vault is identified by a tracked `knowlume.toml` containing only portable relative configuration. Resolution precedence is command-line override, `KNOWLUME_VAULT`, nearest ancestor marker, then user-level default. Ambiguous resolution fails.

Machine paths, credentials, adapter endpoints, locks, and transaction state remain outside tracked durable knowledge. File writes use expected checksums and same-directory atomic replacement. Multi-file use cases use a vault lock, a transaction manifest, same-filesystem staging, and explicit recovery.

## Consequences

- `private` remains an application policy, not a promise about Git or disk encryption.
- Windows and Linux must expose the same conflict and recovery behavior.
- Production write mechanics are implemented in Phase 1; Contract v2 freezes their observable behavior.

## Alternatives considered

- Store knowledge beside application source: rejected because it couples private data to software distribution.
- Infer one global vault without a marker: rejected because automation could target the wrong tree.

