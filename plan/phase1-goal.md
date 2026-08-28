# Phase 1 execution goal: Vault and core

> Status: Complete — all M0–M10 gates passed on 2026-08-28
> Evidence: [CI](https://github.com/yjdy/Knowlume/actions/runs/33120979913) and [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33120979856)
> Intended branch: `Phase1`
> Document role: implementation goal and milestone checklist, not a new contract authority

This document can be used directly as the goal for Phase 1 development. When implementation is
authorized, execute milestones M0 through M10 in order. Do not skip a milestone gate merely because
later work appears to pass. The machine contract remains authoritative in `schemas/v2/`, interface
schemas, and executable tests; semantics and architecture remain authoritative in the active plan
documents and accepted ADRs.

Actual Git commits, pushes, tags, package uploads, and releases require separate explicit user
authorization. A milestone marked “Git commit: Yes” means it should form an independent, green,
reviewable commit when authorization is given; it does not authorize committing by itself.

## 1. Final outcome

After Phase 1 is complete, the installed pure-Python Knowlume core package can operate a separate
Contract v2 vault from any working directory on Windows, macOS, and Linux. It does not depend on the
source checkout, SQLite, Web, or an external adapter.

The following commands are implemented, documented, tested, and marked `Verified` in
[`../CLI.md`](../CLI.md):

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

The user can then:

- explicitly initialize a portable vault and reliably discover it later;
- create, display, and evolve source-free human Notes and sourced Notes;
- scan and semantically validate all Contract v2 objects, Note bodies, locators, and relation shards
  without SQLite;
- receive stable typed diagnostics for configuration, parsing, references, lint, conflicts, and
  recovery;
- safely add, remove, and list canonical relation-shard entries;
- preview v1-to-v2 migration and apply it only when all required decisions and blockers are resolved;
- recover or roll back interrupted multi-file operations without accepting partial success.

The wheel and source distribution are ready for a manually approved TestPyPI internal release. All
publication gates remain closed, and Phase 1 itself uploads nothing.

## 2. Milestone overview

| Milestone | Result | Depends on | Git commit |
|---|---|---|---|
| M0 | clean baseline and requirement map | none | No new commit |
| M1 | frozen Vault/config/transaction/CLI contracts | M0 | Yes — C1 |
| M2 | Contract v2 domain and parser | M1 | Yes — C2 |
| M3 | Vault initialization, discovery, and atomic single-file writes | M2 | Yes — C3 |
| M4 | recoverable multi-file transactions | M3 | Yes — C4 |
| M5 | deterministic scanner, status, and lint | M2–M4 | Yes — C5 |
| M6 | Note create/show/evolve operations | M5 | Yes — C6 |
| M7 | relation add/remove/list operations | M5–M6 | Yes — C7 |
| M8 | v1-to-v2 dry-run and apply migration | M4–M7 | Yes — C8 |
| M9 | package, workflow, CLI ledger, and documentation readiness | M1–M8 | Yes — C9 |
| M10 | complete verification and Phase 1 status transition | M9 | Yes — C10 |

## 3. Milestone work steps

### M0 — Freeze the baseline and map requirements

**Requirements**

- Confirm the current branch, HEAD, upstream relation, and clean/dirty state.
- Preserve all user changes and identify which files are already modified before Phase 1 work begins.
- Run the existing complete repository suite to establish a real baseline.
- Map each Phase 1 command and invariant to its owning schema, interface document, ADR, and future test.
- Record unresolved interface questions rather than silently choosing behavior in production code.

**Limits**

- Read-only inspection only; no production, schema, template, or status changes.
- Do not treat README wording as stronger than executable contracts.
- Do not create or operate on a real personal vault.

**Completion condition**

- Baseline HEAD and test result are recorded.
- No pre-existing user change is mistaken for Phase 1 work.
- Every M1–M10 requirement has an identified authority and verification route.

**Git commit:** No new commit. The existing clean branch point is checkpoint C0. If the baseline is
dirty, obtain user direction before creating any checkpoint.

### M1 — Freeze configuration, transaction, and CLI contracts

**Requirements**

- Record the configuration/transaction decision and migration impact in an accepted ADR.
- Give portable `knowlume.toml` its own versioned schema, template, positive fixtures, negative
  fixtures, and executable acceptance tests.
- Freeze global `--vault PATH`, its interaction with `kb init PATH`, and typed errors for missing,
  invalid, unsupported, conflicting, and ambiguous vaults.
- Version the transaction manifest and define lock, staging, backup, commit, rollback, recovery, and
  cleanup states.
- Freeze any Phase 1 machine-readable result before implementation. Keep object, locator, relation,
  interface, projection, parser, configuration, and transaction versions independent.
- Update schema/template navigation and chapter ownership where needed.

**Limits**

- No production behavior in this milestone.
- Contract v1 remains byte-stable and read-only.
- `knowlume.toml` contains portable relative configuration only; no absolute machine paths,
  credentials, adapter endpoints, locks, or transaction records.
- Follow the repository order: decision and migration impact, schema, template, fixtures, executable
  tests, then production code in later milestones.

**Completion condition**

- All new schemas pass schema self-validation.
- Positive fixtures pass and negative fixtures fail for the intended reason.
- CLI placement, exit behavior, and recovery states have no unresolved ambiguity.
- Existing v1/v2 contract and documentation-link tests remain green.

**Git commit:** Yes — C1, suggested message:
`docs(contract): freeze phase 1 vault and transaction interfaces`.

### M2 — Implement the Contract v2 domain and parser

**Requirements**

- Establish inward-pointing `domain`, `application`, `ports`, adapter, and CLI package boundaries.
- Implement domain values for typed object IDs, stable section IDs, actors, lifecycle state, Note
  type/maturity, citations/locators, AI provenance, and canonical relations.
- Parse and normalize Source, Note, Snippet, and AI Artifact frontmatter; role-based Note sections;
  Fact and AI metadata; locators; and relation shards.
- Support deterministic parse-normalize-render-parse round trips.
- Enforce at least one unique `human` section, per-block Fact citations, promoted AI Artifact
  references, Idea maturity, locator compatibility, and schema constraints.

**Limits**

- Domain code must not depend on Typer, filesystem APIs, Git, SQLite, Zotero, Web, or publishing.
- Titles, headings, line numbers, and filenames are not durable identities.
- Runtime schema/template access uses `importlib.resources`; never search the source checkout or cwd.
- Do not modify durable files in this milestone.

**Completion condition**

- Every maintained v2 positive fixture round-trips without identity or semantic loss.
- Every maintained negative fixture produces a stable typed finding.
- Source-free Idea and Concept parse successfully and remain human provenance, not Facts.
- Parser/domain tests and the complete existing suite pass.

**Git commit:** Yes — C2, suggested message:
`feat(core): add contract v2 domain and parser`.

### M3 — Implement Vault initialization, discovery, and atomic single-file writes

**Requirements**

- Implement `kb init PATH` and the standard `sources`, `notes`, `snippets`, `ai/artifacts`,
  `relations`, and `.knowlume/{locks,transactions}` topology.
- Implement discovery precedence: global `--vault`, `KNOWLUME_VAULT`, nearest ancestor marker, then
  the `platformdirs` user default.
- Validate configuration version, object Contract compatibility, and every configured path.
- Reject traversal, symlink/junction escape, and any write outside the resolved Vault root.
- Implement expected-checksum writes using a same-directory temporary file, flush/fsync as required,
  and atomic replacement.
- Return exit code 4 when a file changes after reading; never overwrite the newer content.

**Limits**

- No implicit vault creation or guessing when discovery is missing or ambiguous.
- No automatic Git operation.
- Installation, upgrade, downgrade, and uninstall must not mutate a vault.
- New durable objects default to `private`; diagnostics do not expose note bodies or unnecessary
  absolute paths.

**Completion condition**

- Discovery priority and every typed failure mode have automated tests.
- Initialization is deterministic and refuses unsafe or conflicting targets without partial output.
- Spaces, Unicode, long paths, read-only directories, traversal, symlink, and junction cases are
  covered where supported by the platform.
- Concurrent modification tests prove the original/newer content is preserved.
- `kb init` command tests and the complete suite pass.

**Git commit:** Yes — C3, suggested message:
`feat(vault): add discovery init and atomic file writes`.

### M4 — Implement recoverable multi-file transactions

**Requirements**

- Implement one Vault write lock, a versioned manifest, same-filesystem staging, backups, ordered
  commit, rollback, recovery, and idempotent cleanup.
- Verify all expected checksums before the first durable replacement.
- Detect unfinished transactions before any new write begins.
- Inject interruption at every transaction state and entry boundary.
- Provide equivalent observable conflict and recovery behavior on Windows and Linux.

**Limits**

- A partially applied operation is never reported or scanned as successful.
- Unsupported manifest versions and unexplained locks fail closed.
- Recovery operates only inside the resolved Vault boundary.
- Do not test against the sole copy of real personal knowledge.

**Completion condition**

- Prepared, committing, rolling-back, and committed interruption tests have deterministic outcomes.
- Recovery and rollback can be run repeatedly without further damage.
- Simultaneous writers and lock contention return stable typed results.
- Crash/recovery tests pass on Windows and Linux and the complete suite remains green.

**Git commit:** Yes — C4, suggested message:
`feat(vault): add recoverable multi-file transactions`.

This is a high-risk checkpoint. Do not start mutation or migration work until C4 is reviewed and
green.

### M5 — Implement scanner, status, and lint

**Requirements**

- Deterministically enumerate durable files and build an in-memory object/section/relation catalog.
- Detect duplicate IDs/sections, invalid layout, missing references, locator mismatch, invalid AI
  state, shard-owner mismatch, relation direction/cardinality errors, and duplicate canonical keys.
- Implement `kb scan`, `kb status`, and `kb lint [--strict|--changed]` through application services.
- Emit stable finding code, severity, object/section/file location, and typed exit behavior.
- Make `status` consume scanner results rather than introduce another parser.

**Limits**

- No SQLite or derived database dependency.
- `--changed` may narrow displayed findings but must not omit cross-file integrity checks.
- Parse failures are reported and never silently erase or hide durable knowledge.

**Completion condition**

- Repeated scans of unchanged files are deterministic.
- All v2 positive/negative, relation, cardinality, provenance, and reference fixtures are covered.
- CLI stdout/stderr, JSON surfaces where defined, help, and exit codes pass command tests.
- Complete suite passes.

**Git commit:** Yes — C5, suggested message:
`feat(core): add scanner status and lint`.

### M6 — Implement Note creation, display, and evolution

**Requirements**

- Implement `note new` from bundled v2 templates with stable typed IDs, at least one human section,
  private visibility, and valid default maturity.
- Treat source-free Idea and Concept as first-class content.
- Implement stable-ID lookup and normalized rendering for `note show`.
- Implement only the accepted Idea-to-Concept transition. Preserve Note ID, every section ID, and body;
  append structured `type_history` with actor and time.
- Use conflict-safe writes and scanner validation before accepting results.

**Limits**

- Idea may only be seed/developing.
- Do not invent other type transitions, merge, or supersession behavior.
- Human content without citations must not be converted to Fact.
- Machine-readable output requires a versioned interface contract first.

**Completion condition**

- Every Note type can be created and scanned from an installed wheel.
- Source-free Note tests pass.
- Idea-to-Concept round trip proves ID/section/body preservation and correct history.
- Invalid transition and concurrent-edit cases fail without modifying the Note.
- Command tests and complete suite pass.

**Git commit:** Yes — C6, suggested message:
`feat(notes): add note creation display and evolution`.

### M7 — Implement sharded relation operations

**Requirements**

- Implement relation add/remove/list using only `relations/<from_id>.yaml` as durable authority.
- Validate shard ownership, target object/stable section, relation direction matrix, same-kind
  supersession, canonical single storage of `related_to`, canonical-key uniqueness, normalized
  locator, actor, and timestamp.
- Derive inverse relations from scanning; do not duplicate backlinks.
- Use safe writes and transaction recovery as appropriate.

**Limits**

- Do not restore `source_ids`, `related_notes`, or supersession fields to Note frontmatter.
- AI output cannot directly write a trusted relation.
- Removing a relation requires an exact canonical-key match and must not remove nearby entries.

**Completion condition**

- Direction, kind, section, ownership, uniqueness, symmetry, locator, actor, add/remove/list, conflict,
  and no-partial-write tests pass.
- Relation cardinality findings remain scanner/lint responsibilities and are consistent after edits.
- Command tests and complete suite pass.

**Git commit:** Yes — C7, suggested message:
`feat(relations): add sharded relation operations`.

### M8 — Implement v1-to-v2 migration

**Requirements**

- Implement dry-run as the default with no durable writes.
- Emit migration-report v1 with mechanical changes, human decisions, blockers, and prohibited
  inference clearly distinguishable.
- Preserve fixed v1 section IDs while mapping their roles. Mechanically convert `related_notes`,
  supersession fields, global relations, and one Literature source into relation shards.
- Report Evergreen classification, ambiguous non-Literature `source_ids`, missing per-block locators,
  unaudited AI, duplicate/missing identities, and dangling references as decisions or blockers.
- Allow apply only with zero unresolved required decisions and blockers, using the M4 transaction
  protocol.

**Limits**

- Never guess `cites` or `synthesizes`.
- Fixed v1 sections and `sec_original_facts` are migration inputs only.
- Failure leaves the original vault usable and no partial migration accepted.
- Migration never runs during package install, upgrade, or startup.

**Completion condition**

- Mechanical, decision, blocker, prohibited-guess, no-write dry-run, blocked apply, successful apply,
  crash, recovery, and idempotency tests pass.
- Migrated results pass full v2 scan/lint.
- V1 historical contract tests remain green.
- Command tests and complete suite pass.

**Git commit:** Yes — C8, suggested message:
`feat(migrate): add recoverable v1 to v2 migration`.

This is a high-risk checkpoint. Use disposable copies only and review C8 independently before any
status or release change.

### M9 — Complete package, workflow, CLI ledger, and documentation readiness

**Requirements**

- Synchronize command names, options, help, stdout/stderr, JSON envelope, typed errors, and exit codes
  0–6 with interfaces and the CLI ledger.
- Update CLI status only where command-level tests and the full suite provide evidence.
- Keep README, roadmap, interfaces, schema/template READMEs, and chapter-map navigation consistent.
- Correct release-job conditions so a TestPyPI-only Phase 1 flow can skip formal PyPI and GitHub
  Release jobs rather than fail because those gates are closed.
- Audit wheel/sdist contents and bundled-resource byte equality.

**Limits**

- Keep all publication gates closed and upload nothing.
- Core imports and Phase 1 commands cannot require Web/Zotero extras.
- The wheel excludes plans, tests, fixtures, vaults, databases, caches, credentials, build output, and
  machine-specific paths.
- Do not mark Phase 1 complete in this milestone.

**Completion condition**

- CLI help exactly matches the registered Phase 1 inventory.
- Wheel/sdist verification and isolated-install smoke tests pass from an arbitrary cwd.
- Install/upgrade/downgrade/uninstall tests prove the vault is unchanged.
- Release workflow contract tests prove closed gates skip unauthorized stages.
- Complete suite, Ruff, and mypy pass.

**Git commit:** Yes — C9, suggested message:
`build(release): verify phase 1 package boundary`.

### M10 — Run the final gate and change status

**Requirements**

- Perform the requirement-by-requirement completion audit in section 5.
- Collect direct local, distribution, isolated-install, and CI evidence.
- Mark only commands with command-level evidence and a passing full suite as `Verified`.
- Change README/roadmap status to `Phase 1 Complete` only after every required gate is proven.

**Limits**

- Do not substitute “no observed failure” for missing test coverage.
- Do not waive Windows/Linux recovery evidence or any unresolved migration case.
- Do not open TestPyPI/PyPI gates or publish without separate authorization.

**Completion condition**

- Every item in sections 4 and 5 is directly proven, not inferred.
- All Phase 1 commands are verified and no Phase 1 requirement is deferred.
- Final diff contains no private/generated/environment-specific material.
- Repository status documents and CLI ledger match the evidence exactly.

**Git commit:** Yes — C10, suggested message: `docs: mark phase 1 complete`. This commit contains
status declarations only and is reverted immediately if any supporting evidence is invalidated.

## 4. Requirements that apply to every milestone

### Contract and knowledge integrity

- Production creates and modifies Contract v2 only; Contract v1 is read only through migration.
- Preserve object IDs across rename, move, merge, and supersession; preserve section IDs across heading
  and Note-type changes.
- Every v2 Note has a human section. Human thought may be source-free; Facts require valid
  Source/locator citations; AI blocks require promoted Artifacts.
- Relations target existing objects or stable sections and are written only to their source shard.
- Never use line numbers, headings, filenames, SQLite rows, or caches as the only durable identity or
  source of a business fact.

### Safety, privacy, and distribution

- Preserve unrelated user work and inspect dirty files before editing.
- Never overwrite content changed since it was read.
- Never track personal knowledge, credentials, tokens, attachment bodies, absolute machine paths,
  databases, caches, logs, temporary repositories, or public staging.
- Application `private` is not encryption or Git-remote protection.
- Package and Contract upgrades remain independent; no implicit migration.
- No Git commit, stage, push, history rewrite, branch deletion, package upload, or release without
  explicit user authorization.

### Scope boundary

Phase 1 excludes paper/Zotero capture, unified Web/Book/OSS capture, SQLite projection and search,
Web UI, AI review/promotion, merge/history/backlinks, secure publishing, semantic/hybrid search, MCP,
graph databases, and multi-agent workflows.

## 5. Checks required before Phase 1 completion

### Functional and failure coverage

The automated suite must cover:

- configuration schema and all four discovery priorities;
- missing, invalid, unsupported, conflicting, and ambiguous Vaults;
- spaces, Unicode, long paths, read-only directories, traversal, symlinks, and junctions;
- expected-checksum conflicts, simultaneous writers, lock contention, every crash boundary, recovery,
  rollback, and recovery idempotency;
- round trips for every v2 object, Note body, locator, and relation form;
- duplicate IDs/sections, missing references, Fact citations, AI promotion, relation ownership,
  direction, cardinality, canonicalization, and uniqueness;
- source-free Notes and Idea-to-Concept identity/history preservation;
- all Note and relation commands, including invalid input, conflict, and no-partial-write paths;
- migration mechanical changes, decisions, blockers, prohibited guesses, dry-run no-write behavior,
  blocked apply, successful apply, and interrupted-apply recovery;
- CLI help inventory, stdout/stderr separation, JSON golden files, stable typed errors, and exit codes.

### Required local checks

Run the smallest relevant checks during each milestone. Before M10 completes, run and pass:

```powershell
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests scripts
uv run --no-sync mypy src tests scripts
```

Existing v1 historical tests, all Phase 0R contracts and fixtures, and internal documentation links
must remain green.

### Cross-platform and distribution checks

- CI passes on Windows, macOS, and Linux with Python 3.13 and 3.14.
- Atomic replacement, conflict handling, lock behavior, and crash recovery pass fully on Windows and
  Linux.
- Build wheel and sdist, run `scripts/verify_distribution.py`, and prove bundled schemas/templates are
  byte-identical to repository authorities.
- Install the wheel outside the checkout. From an arbitrary cwd and using temporary vaults, smoke-test
  `--version`, `--help`, `doctor`, and every Phase 1 command.
- Verify installation, upgrade, downgrade, and uninstall do not alter the temporary vault.
- Verify unsupported newer configuration and object Contracts fail closed.

### Final repository audit

- Review the complete diff and tracked-file list.
- Confirm no unrelated user change was lost.
- Confirm no private knowledge, credentials, absolute machine paths, caches, databases, temporary
  vaults, build artifacts, or publication output are tracked.
- Confirm CLI.md, README, roadmap, interfaces, schema/template navigation, and implementation evidence
  agree.

## 6. Git checkpoint and rollback rules

1. Each “Git commit: Yes” milestone forms one independently reviewable commit only after its targeted
   checks and the complete suite are green.
2. C1 owns contracts; do not hide schema changes in later CLI commits. C4, C8, and C9 are mandatory
   review boundaries before proceeding because they affect recovery, migration, and distribution.
3. If a committed milestone is wrong, prefer `git revert <commit>`. Revert dependent commits in
   reverse order. Do not use `git reset --hard` as a recovery procedure.
4. C2 and later depend on C1. C5–C8 depend on the safe-write foundations. Reverting C4 requires
   reverting every later consumer first. Reverting C7 after C8 requires reverting C8 first.
5. Mutation and migration tests use disposable Vault copies. Git rollback is not a substitute for
   backing up real personal knowledge.
6. If a milestone is not green, fix it before beginning the next milestone; never create C10 while a
   command is only `Implemented` or required CI evidence is missing.

## Definition of done

Phase 1 is complete only when every deliverable, invariant, command, failure mode, and platform gate
in this document has direct evidence and no required work is hidden under a later phase. The absence
of a failing test is insufficient when a required scenario has no test or other authoritative proof.
