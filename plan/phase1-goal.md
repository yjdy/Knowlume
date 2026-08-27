# Phase 1 execution goal: Vault and core

> Status: Execution brief — not an independent contract authority  
> Applies to: the `Phase1` development branch  
> Authorities: [`roadmap.md`](roadmap.md), [`interfaces.md`](interfaces.md),
> [`architecture.md`](architecture.md), [`data-model.md`](data-model.md),
> [`storage-index-search.md`](storage-index-search.md), accepted ADRs, versioned schemas, and
> executable tests

This document is a directly reusable implementation goal. It organizes Phase 1 work and acceptance
without redefining machine fields or replacing the authoritative documents above.

## Goal

Implement and verify Knowlume Phase 1 in the current `Phase1` branch. Preserve existing user work.
Do not create another branch, commit, push, publish a package, or create a release unless the user
explicitly requests that action. Work contract-first and keep Contract v1 read-only.

## 1. What Phase 1 must deliver

At completion, the installed pure-Python core package can safely operate an independent Contract v2
vault on Windows, macOS, and Linux from any working directory. It does not depend on the source
checkout, SQLite, Web, or an external adapter.

The following commands are implemented, documented, covered by command-level tests, and marked
`Verified` in [`../CLI.md`](../CLI.md):

```text
kb init PATH
kb scan
kb status
kb lint [--strict|--changed]
kb note new --type idea|literature|concept|synthesis
kb note show ID
kb note evolve ID --to concept
kb relation add FROM_ID TO_ID --type TYPE
kb relation remove FROM_ID TO_ID --type TYPE
kb relation list ID
kb migrate --from 1 --to 2 [--dry-run|--apply]
```

A user can:

- explicitly initialize a portable vault and reliably discover it later;
- create and read source-free human Notes as well as sourced Notes;
- evolve an Idea to a Concept without changing the Note or section identities;
- scan all durable v2 objects, Note bodies, locators, and relation shards without SQLite;
- receive stable, typed status, lint, parse, reference, conflict, and recovery diagnostics;
- add, remove, and list canonical relation-shard entries safely;
- preview v1-to-v2 migration and apply it only when all required decisions and blockers are resolved;
- recover or roll back an interrupted multi-file operation without accepting partial success.

The wheel and source distribution are ready for a manually approved TestPyPI internal release. All
release gates remain closed and no upload occurs as part of Phase 1 implementation.

## 2. Requirements that cannot be omitted

### 2.1 Contract-first prerequisites

Before production implementation, freeze the remaining Phase 1 surfaces:

- Give portable `knowlume.toml` an independent configuration version, schema, template, positive and
  negative fixtures, and executable tests. Do not reuse the object Contract version as its format
  version.
- Define `--vault PATH` as a shared CLI option, its interaction with `kb init PATH`, and stable typed
  errors for missing, invalid, unsupported, conflicting, or ambiguous vaults.
- Version the transaction manifest and define lock, staging, commit, recovery, rollback, and cleanup
  states. Crash recovery must not depend on guessing what happened.
- Freeze any Phase 1 JSON result or error surface before emitting it. Object, locator, relation,
  interface, projection, parser, configuration, and transaction versions remain independent.
- For an incompatible durable or machine-interface change, follow the repository order: decision and
  migration impact, schema, template, fixtures, tests, production implementation, migration behavior.

Contract v1 schemas, templates, and fixtures remain historical inputs. Production creates and edits
Contract v2 only. Fixed v1 sections, including `sec_original_facts`, must never become v2 authoring
requirements.

### 2.2 Architecture and package boundaries

- Implement clear `domain`, `application`, `ports`, filesystem/config adapters, and `cli` layers.
  Dependencies point inward; CLI calls application services rather than duplicating business rules.
- Domain code must not depend on Typer, filesystem APIs, Git, SQLite, Zotero, Web, or publishing
  frameworks.
- Installed runtime schemas and templates are read only through `importlib.resources`; runtime code
  must not search the source checkout or current directory.
- Keep the core wheel pure Python and independent from optional `web` and `zotero` extras.
- Do not implement Phase 2+ work: capture/adapters, SQLite/search, Web, AI review/promotion,
  publishing, semantic search, MCP, graph, or multi-agent features.

### 2.3 Vault and configuration behavior

- Program installation and personal vaults remain separate. No command implicitly creates a vault.
- Discovery order is global `--vault`, `KNOWLUME_VAULT`, nearest ancestor `knowlume.toml`, then the
  `platformdirs` user default. Conflicting or ambiguous candidates fail closed.
- `kb init` creates the standard `sources`, `notes`, `snippets`, `ai/artifacts`, `relations`, and
  `.knowlume/{locks,transactions}` topology.
- Tracked configuration contains portable relative paths only. Absolute machine paths, credentials,
  adapter endpoints, locks, and transaction state remain machine-local.
- Reject traversal and symlink/junction escape. Handle spaces, Unicode, long paths, non-empty targets,
  and read-only directories with deterministic typed outcomes.
- Do not perform implicit Git operations. Installation, upgrade, downgrade, and uninstall must not
  migrate, move, or delete a vault. Unsupported configuration or Contract versions fail closed.

### 2.4 Safe writes and recovery

- Single-file writes use an expected checksum, a temporary file in the destination directory,
  flush/fsync as required for equivalent observable behavior, and atomic replacement. A file changed
  after reading produces exit code 4 and is never overwritten.
- Multi-file writes use one vault write lock, a versioned manifest, same-filesystem staging, backups,
  and explicit recovery. An interruption is detectable; recovery or rollback is idempotent; partial
  output is never treated as a successful transaction.
- Windows and Linux expose the same conflict, lock, replacement, and recovery outcomes. Exercise
  concurrent writers and crash injection at each transaction state.
- New objects default to `private`. Logs and diagnostics do not expose note bodies, credentials, or
  unnecessary absolute vault paths.

### 2.5 Domain, parsing, scanning, status, and lint

- Implement Contract v2 domain values for typed object IDs, stable section IDs, actors, lifecycle
  state, Note type/maturity, citations/locators, AI provenance, and relations.
- Parse and round-trip Source, Note, Snippet, and AI Artifact frontmatter; role-based Note sections;
  Fact and AI metadata; locators; and relation shards. Titles, headings, line numbers, and filenames
  are not durable identities.
- Enforce at least one unique `human` section per Note. Human content may have no Source. Each Fact
  block has one or more type-compatible Source/locator citations. Each AI block references a promoted
  Artifact.
- Scan durable files deterministically and build an in-memory object/section catalog. Detect duplicate
  identities, invalid layout, missing references, locator mismatches, invalid Artifact state, shard
  ownership errors, relation direction/cardinality errors, and duplicate canonical relation keys.
- `lint` emits stable finding codes, severity, and object/section/file location. `--strict` blocks all
  contract and integrity errors. `--changed` may narrow presentation but must not skip cross-file
  reference validation.
- `status` consumes scanner results; it must not introduce a second parser or ruleset.

### 2.6 Note and relation operations

- `note new` uses bundled v2 templates, creates stable typed IDs and a human section, defaults to
  private, and restricts Idea maturity to seed/developing. Source-free Idea and Concept are first-class
  and must not be reclassified as Facts.
- `note show` resolves stable ID and renders the normalized Note. Any machine-readable form requires a
  versioned interface first.
- `note evolve` implements only Idea-to-Concept. It preserves Note ID, section IDs, and body, appends
  structured `type_history`, and rejects illegal transitions or concurrent changes.
- Relations are authoritative only in `relations/<from_id>.yaml`; do not restore relation fields to
  Note frontmatter.
- Relation commands validate shard ownership, target object/section, the allowed direction matrix,
  same-kind supersession, canonical single storage of `related_to`, canonical-key uniqueness,
  locator normalization, actor, and time. AI does not directly write trusted relations; inverse
  relations are derived from scanning.

### 2.7 V1-to-v2 migration

- Dry-run is the default and causes no writes. The report conforms to migration-report v1 and
  distinguishes mechanical changes, human decisions, blockers, and prohibited inference.
- Preserve fixed v1 section IDs while mapping them to v2 roles. Mechanically convert `related_notes`,
  supersession fields, global relations, and one Literature source into relation shards.
- Evergreen classification, ambiguous non-Literature `source_ids`, missing per-block locators,
  unaudited AI, duplicate/missing identities, and dangling references become decisions or blockers.
  Never guess `cites` or `synthesizes`.
- Apply is allowed only with zero unresolved required decisions and blockers. It uses the recoverable
  multi-file protocol; failure leaves the original vault usable and no partial migration accepted.

### 2.8 CLI, documentation, and release foundation

- Keep command names, parameters, help, stdout/stderr, JSON envelope, and exit codes 0–6 aligned with
  interfaces, interface schemas, and the CLI ledger.
- Update README, roadmap, interfaces, CLI ledger, schema/template READMEs, and chapter map when their
  owned status or navigation changes. Do not declare Phase 1 complete early.
- Correct the release workflow so a Phase 1 TestPyPI-only run can skip formal PyPI and GitHub Release
  jobs instead of failing because their gates are closed. Keep every publication gate fail closed.
- The wheel excludes plans, tests, fixtures, vaults, databases, caches, credentials, and machine paths.

## 3. Checks required before completion

### 3.1 Automated behavior

Add positive, negative, conflict, and recovery tests for:

- configuration schema and all four vault-discovery levels;
- missing, invalid, unsupported, ambiguous, and conflicting vaults;
- spaces, Unicode, long paths, read-only directories, traversal, symlinks, and junctions;
- checksum conflicts, simultaneous writers, lock contention, crash injection, idempotent recovery,
  and rollback;
- parse-normalize-render-parse round trips for every v2 object/body/locator/relation form;
- duplicate IDs/sections, missing references, Fact citations, AI promotion, relation ownership,
  direction, cardinality, canonical storage, and uniqueness;
- source-free Ideas/Concepts and Idea-to-Concept identity/history preservation;
- Note and relation command success, invalid input, conflict, and no-partial-write paths;
- migration mechanical changes, decisions, blockers, prohibited guesses, no-write dry-run, blocked
  apply, successful apply, and interrupted-apply recovery;
- CLI help inventory, stdout/stderr separation, JSON golden files, typed errors, and exit codes.

### 3.2 Repository checks

Run the smallest relevant tests while working. Before completion, all of these must pass:

```powershell
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests scripts
uv run --no-sync mypy src tests scripts
```

The existing v1 historical tests, Phase 0R tests, fixtures, and internal documentation-link checks
must remain green. Compare `kb --help` and every subcommand help page against the CLI ledger.

### 3.3 Cross-platform and distribution checks

- CI passes on Windows, macOS, and Linux with Python 3.13 and 3.14. Atomic writes, conflicts, and
  crash recovery pass fully on Windows and Linux.
- Build wheel and sdist; run `scripts/verify_distribution.py`; prove bundled schemas/templates match
  repository authorities byte-for-byte.
- Install the wheel outside the checkout and run every Phase 1 command from an arbitrary directory
  against temporary vaults.
- Verify installation, upgrade, downgrade, and uninstall do not alter a vault, and unsupported newer
  config/Contract versions fail closed.
- Inspect the final diff and tracked contents for lost user changes, private knowledge, credentials,
  absolute machine paths, caches, databases, temporary vaults, and build output.

Only after all required local checks, artifact audits, isolated-install checks, and CI evidence pass
may README/roadmap say `Phase 1 Complete`. A CLI command becomes `Verified` only with command-level
automated evidence and the passing complete suite.

## 4. Git checkpoints and rollback boundaries

Do not combine all Phase 1 work into one commit. Each checkpoint below should be independently
reviewable and green before beginning the next one. Commit creation still requires explicit user
authorization under repository rules.

| Checkpoint | Suggested commit | Contents and required pre-commit evidence | Rollback effect |
|---|---|---|---|
| C0 | existing clean Phase 1 baseline | Confirm branch, HEAD, clean status, and baseline full suite before editing. | The fixed point to return to if the Phase 1 approach is abandoned. |
| C1 | `docs(contract): freeze phase 1 vault and transaction interfaces` | ADR/config and transaction schemas, templates, fixtures, typed errors, global `--vault` semantics, contract/link tests. No production behavior. | Safe to revise alone before implementation; later commits depend on its formats. |
| C2 | `feat(core): add contract v2 domain and parser` | Domain values and parsers with schema and round-trip tests; no filesystem writes. | Revert C2 and every later code commit if the in-memory model is wrong; C1 may remain for redesign. |
| C3 | `feat(vault): add discovery init and atomic file writes` | Config loader, discovery, path boundary, `init`, single-file conflict-safe writes, targeted cross-platform tests. | Revert before any transaction or mutation commit; temporary test vaults remain disposable. |
| C4 | `feat(vault): add recoverable multi-file transactions` | Lock, manifest, staging, backup, crash injection, recovery/rollback tests. | High-risk boundary: revert C4 and all consumers together if recovery semantics are wrong. |
| C5 | `feat(core): add scanner status and lint` | Deterministic scanner/catalog, semantic validators, typed findings, `scan/status/lint`, command tests. | Revert without changing durable files created by C3; later mutations depend on the scanner. |
| C6 | `feat(notes): add note creation display and evolution` | `note new/show/evolve`, bundled templates, identity/history and conflict tests. | Revert C6 before relation/migration commits; test Notes can be discarded. |
| C7 | `feat(relations): add sharded relation operations` | Relation add/remove/list, canonicalization, actor/time, conflict and semantic tests. | Revert C7 independently if C8 has not used relation writes; otherwise revert C8 first. |
| C8 | `feat(migrate): add recoverable v1 to v2 migration` | Report generation, decisions/blockers, prohibited guessing, dry-run/apply, transaction recovery tests. | Revert C8 first. Never test rollback against the only copy of a real vault. |
| C9 | `build(release): verify phase 1 package boundary` | CLI inventory/docs, conditional TestPyPI workflow, wheel allowlist, isolated install and smoke tests; gates remain closed. | Revert release/docs changes without reverting core behavior unless interfaces also changed. |
| C10 | `docs: mark phase 1 complete` | Status-only changes made after every final gate has evidence. | Revert immediately if any claimed evidence is later invalidated. |

### Checkpoint rules

1. Before C1, record the clean baseline HEAD. Before C4, C8, and C9, ensure the preceding checkpoint is
   committed and green; these are the highest-risk recovery, migration, and distribution boundaries.
2. Keep contract changes, production behavior, migration, and status declarations in their designated
   commits. Do not hide a schema change inside a later CLI commit.
3. Use temporary copies of fixtures and vaults for mutation and migration testing. Never use the sole
   copy of personal knowledge to validate rollback.
4. Prefer `git revert <commit>` for a committed checkpoint. Revert dependent commits in reverse order.
   Do not use destructive history rewriting or `git reset --hard` as a recovery procedure.
5. If a checkpoint fails its tests, fix it before the next commit. Do not create C10 while any command
   is merely `Implemented` or while required CI evidence is missing.

## Definition of done

Phase 1 is done only when every deliverable and invariant above has direct evidence, every named
command is verified, the complete repository and distribution gates pass, and no required work is
being deferred under the Phase 1 label. Absence of a failing test is not sufficient when a required
scenario lacks coverage.
