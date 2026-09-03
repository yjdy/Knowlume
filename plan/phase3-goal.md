# Phase 3 execution goal: Deterministic projection, search, and context

> **Status:** Complete — M0–M9 gates passed
> **Target branch:** `Phase3`
> **Implementation baseline commit:** `758554bcae2d73fc2399219dd6f7436a6e3dbe74`
> **Baseline state:** Phase 2B PR #2 is merged into `main`; the target branch starts from that merge
> **Feature evidence:** [CI](https://github.com/yjdy/Knowlume/actions/runs/33300551834) and [package smoke](https://github.com/yjdy/Knowlume/actions/runs/33300551847) passed for `09c4a634a9fdf196dee0e7efe066ce3ab7eafd01`; PyPI Trusted Publisher control was confirmed by the release owner on 2026-09-03

## 1. Current foundation and authority

Phase 0R, Phase 1, Phase 2A, and Phase 2B are complete. Phase 3 reuses:

- Contract v2 objects, role-based Note bodies, typed locators, relation shards, and executable
  projection DDL v2;
- Phase 1 Vault discovery, Contract v2 parser/scanner, typed findings, conflict-aware writes, and
  recoverable transactions;
- Phase 2A and 2B Source provenance, canonical identities, workflow commands, and unified capture;
- CLI envelope v1, packaged resources through `importlib.resources`, distribution audit, isolated
  installation, and supported-platform CI;
- the release pipeline's fail-closed TestPyPI, PyPI prerelease, and stable gates, with the first two
  opened only at M9 after feature CI and project-name control were proven.

This goal is subordinate to machine schemas and follows:

- [`roadmap.md`](roadmap.md);
- [`ADR-0001`](decisions/0001-files-as-source-of-truth.md);
- [`ADR-0003`](decisions/0003-locator-and-stable-sections.md);
- [`ADR-0008`](decisions/0008-ai-promotion-and-publish-dependencies.md);
- [`ADR-0010`](decisions/0010-python-package-distribution.md);
- [`ADR-0016`](decisions/0016-phase3-deterministic-projection-search-context.md);
- [`storage-index-search.md`](storage-index-search.md);
- [`interfaces.md`](interfaces.md);
- [`security-publishing.md`](security-publishing.md);
- the current Contract v2 and interface schemas.

Implementation extends the existing Domain, Application, Port, Adapter, CLI, Vault, and resource
boundaries. It must not introduce a second parser, make SQLite durable, or bypass scanner and
publishing policy.

## 2. Final outcome

After Phase 3, Knowlume provides:

```text
kb grep QUERY [--limit N] [--json]
kb get ID [--json]
kb index build [--json]
kb index rebuild [--json]
kb index status [--json]
kb search QUERY [filters] [--scope trusted-local|public-safe] [--limit N] [--json]
kb context QUERY --scope trusted-local|public-safe [--limit N] [--max-chars N] [--json]
```

`grep` and `get` work without SQLite. Index commands create and maintain a disposable projection at
`<vault>/<configured state>/kb.sqlite`. Search performs deterministic bilingual FTS over traceable
segments. Context groups bounded, cited material under an explicit trust scope without sending data
to an external model.

Deleting `kb.sqlite` and rebuilding from the same durable bytes with the same interpretation
versions yields an equivalent normalized projection. Every search result returns to a permanent
object ID, vault-relative file, projection segment ordinal, and durable Note section ID when one
exists. Generated segment IDs never become durable references.

Phase 3 opens release eligibility only after all feature and package gates pass and PyPI project-name
control is proven. It does not publish a package, change the package version, create a tag, or create
a GitHub Release.

## 3. Frozen interfaces and behavior

### 3.1 Database lifecycle

- The only default database path is `vault.path("state") / "kb.sqlite"`; no config field is added.
- `index build` creates a full index when absent and otherwise performs a checksum-based incremental
  update.
- `index rebuild` always builds a validated sibling temporary database and atomically replaces the
  target only after a healthy, unchanged Vault snapshot is proven.
- `index status` is read-only and reports `missing`, `fresh`, `stale`, `incompatible`, or `corrupt`.
- `search` and `context` require a fresh compatible database and never auto-build or auto-repair.
- A version mismatch or corrupt database requires explicit rebuild.
- Index writers use a state-local non-blocking lock and never hold or reinterpret the durable Vault
  transaction lock.

### 3.2 Projection source and ordering

- `scan_vault` output is the only projection input.
- A scan with any error finding cannot be promoted as a new full projection.
- Rows use normalized domain values, canonical JSON, relative paths, and stable deterministic
  ordering.
- Note blocks map one-to-one to segments and retain role, section, ordinal, citations, and promoted
  Artifact identity.
- Source, Snippet, and AI Artifact bodies use projection-only `__body__`; public results expose no
  durable section ID for that sentinel.
- Segment ID derivation follows ADR-0016 `segment-v1` exactly and is never stored in Vault files.
- Determinism is asserted over logical content rows and stable metadata, not SQLite page bytes or
  operational timestamps.

### 3.3 Tokenizer v1

- Add `TOKENIZER_VERSION = 1` without changing parser or projection versions.
- Apply NFKC and case-folding to indexed text and queries.
- Emit Unicode letter/number runs as tokens.
- Emit every Han character followed by every adjacent Han bigram using the frozen ADR-0016 range
  table and ordering.
- Treat user queries as literal terms; never pass raw FTS syntax.
- Record tokenizer and segment-algorithm versions in index metadata, and add only the tokenizer
  version to `kb --version`.
- Add no tokenizer dependency, network model, custom SQLite extension, or platform-native wheel.

### 3.4 File search and object retrieval

`kb grep` scans only configured durable object and relation roots. It may report private and AI files
because it is explicitly a trusted-local diagnostic. It excludes configuration, state, attachments,
caches, and generated output. Results sort by relative path, line, and column. Line and column are
ephemeral navigation aids.

`kb get` resolves a permanent object ID through the scanner and returns normalized object fields,
body, path, checksum, citations, and incoming/outgoing relations. It does not probe adapters or
create an index. Missing IDs use `OBJECT_NOT_FOUND`.

### 3.5 Search filters and defaults

The Phase 3 search syntax is:

```text
kb search QUERY
  [--kind source|note|snippet|ai_artifact]
  [--subtype VALUE]
  [--visibility private|public]
  [--record-status active|archived|superseded]
  [--workflow-stage inbox|reading|processed|integrated]
  [--maturity seed|developing|mature|evergreen]
  [--review-status unreviewed|accepted|rejected|promoted]
  [--tag TAG]...
  [--role source|human|fact|ai|evolution|snippet]
  [--scope trusted-local|public-safe]
  [--limit N]
  [--json]
```

- Query must contain at least one tokenizer term.
- Default scope is `trusted-local`, default limit is 20, and maximum limit is 200.
- Repeated tags use AND semantics; all other supplied filters are conjunctive.
- Defaults include private and public active Source, human, fact, and snippet results.
- Defaults exclude archived, superseded, AI Artifact, and AI segment results.
- Explicit AI kind/role filtering is valid only for trusted-local. A Note AI block still requires a
  promoted Artifact; raw Artifact bodies are never public-safe.
- Ranking is BM25 followed by object ID, public section ID or empty string, and ordinal.
- Every hit includes result classification, relative path, object identity, section when durable,
  segment ID/ordinal, snippet, score, tags, visibility/status, and citations.

### 3.6 Context assembly

The Phase 3 context syntax is:

```text
kb context QUERY --scope trusted-local|public-safe
  [--limit N]
  [--max-chars N]
  [--json]
```

- Scope is required; there is no inferred default.
- Default result limit is 20, maximum is 200, default character budget is 12,000, and the accepted
  maximum is 100,000.
- Output groups are Sources, Facts, Human Notes, and Snippets in that order.
- Within each group, ranking and deterministic tie-breaks match search.
- Whole items are added until the budget is reached; an individual item is not cut mid-text. The
  result reports `character_count`, `truncated`, and excluded candidates.
- Phase 3 context never returns AI Artifact bodies or Note AI blocks.
- `public-safe` applies the complete per-result eligibility rules from ADR-0016 and reports an
  exclusion code for each unsafe candidate while retaining safe results.
- A public-safe context result is not a Phase 6B publish audit or staging manifest.

### 3.7 Machine results

All Phase 3 JSON output is one CLI envelope v1 document. New result schemas are:

| Schema | Commands | Required result content |
|---|---|---|
| `grep-result-v1` | `grep` | query, limit, hits with relative path/line/column/excerpt and optional object/section identity |
| `get-result-v1` | `get` | normalized object/body, relative path, checksum, citations, incoming/outgoing relations |
| `search-result-v1` | `search` | query, scope, filters, index versions, ranked traceable hits |
| `context-result-v1` | `context` | query, scope, groups, citations, exclusions, character count, truncation |
| `index-result-v1` | `index build/rebuild/status` | operation, state, versions, snapshot, counts, changed paths, findings |

Schemas reject absolute paths, unknown enum values, invalid limit/state combinations, missing
identity for a search hit, and public-safe items without the required audit result. Each receives
valid, invalid, and golden CLI fixtures before command registration.

### 3.8 Refresh coupling

After a durable mutation successfully commits, the application requests incremental refresh only if
a compatible index exists. This applies to capture, Source synchronization/workflow, Note
creation/evolution, relation add/remove, and applied migration. Index absence is a no-op. Refresh
failure returns `INDEX_REFRESH_FAILED` as a warning, never rewrites the durable success result, and
causes later status/search behavior to identify stale state.

Refresh is an application service concern. Domain code and durable-write adapters do not import
SQLite, and optional index failure cannot make a completed mutation appear rolled back.

### 3.9 Diagnostics

Public errors and exits are frozen by ADR-0016:

| Code | Exit |
|---|---:|
| `INDEX_NOT_FOUND` | 5 |
| `INDEX_INCOMPATIBLE` | 3 |
| `INDEX_CORRUPT` | 3 |
| `INDEX_SOURCE_INVALID` | 3 |
| `INDEX_SOURCE_CHANGED` | 4 |
| `INDEX_BUSY` | 4 |
| `SEARCH_QUERY_INVALID` | 2 |
| `OBJECT_NOT_FOUND` | 3 |

`INDEX_REFRESH_FAILED` is a warning on an otherwise successful mutation. Public messages never
include SQL, absolute paths, private text, temporary names, SQLite internals, or environment values.

## 4. Requirements that cannot be omitted

- Markdown/YAML and relation shards remain the durable authority.
- No Phase 3 operation modifies object, body, locator, relation, configuration, or transaction
  contracts.
- Projection DDL v2 remains byte-authoritative and bundled wheel bytes match the top-level file.
- Index construction uses the installed resource, never a source checkout or current directory.
- Full rebuild is failure-atomic and incremental build is transaction-atomic.
- Concurrent changes are detected before commit; no scan result silently overwrites newer state.
- A stale, incompatible, or corrupt index cannot serve ordinary search or context.
- Search results always explain their durable origin and provenance classification.
- Source-free human text remains human opinion with empty citations, never Fact.
- Facts retain all citations in declared order.
- AI is excluded by default, and context excludes it for the whole phase.
- Public-safe filtering cannot widen visibility or dependency eligibility.
- Existing Phase 1 and Phase 2 commands continue to work with no index present.
- Package installation and removal never create, rebuild, migrate, or delete a Vault index.
- No SQLite database, journal, lock, cache, or generated context enters a wheel or sdist.

## 5. Milestones and Git checkpoints

Git commands remain separately authorized. Suggested commits are rollback boundaries, not
authorization to stage, commit, push, merge, tag, or publish.

### M0 — Freeze the Phase 3 decision

**Work**

- Accept ADR-0016.
- Create this execution goal.
- Synchronize active storage/search, interface, roadmap, CLI ledger, plan navigation, and ownership
  documents.
- Keep every Phase 3 CLI row `Planned` with no verification claim.

**Completion conditions**

- The database path, rebuild/build semantics, segment algorithm, tokenizer, query defaults,
  public-safe behavior, JSON schema names, diagnostics, and release boundary have one owner.
- Documentation links pass and no active document contradicts the ADR.
- No production code, schema, fixture, dependency, DDL, release gate, or version changes are included.

**Git commit:** Yes — P3-C1

```text
docs: freeze phase 3 projection and search design
```

### M1 — Freeze Phase 3 machine contracts

**Work**

- Add the five result schemas and register them in interface documentation and contract tests.
- Add valid, invalid, and golden envelope fixtures for every command family.
- Add the tokenizer version to the runtime version report and record the segment-algorithm version
  in index compatibility metadata.
- Freeze public result enums, limit ranges, relative-path constraints, and diagnostics.

**Completion conditions**

- Every JSON success path validates against exactly one explicit result schema inside envelope v1.
- Negative fixtures reject absolute paths, missing provenance, unsafe public-safe claims, and invalid
  operation/state combinations.
- Existing interface schemas and fixtures remain valid.
- Projection DDL v2 remains unchanged.

**Git commit:** Yes — P3-C2

```text
feat(contract): add phase 3 query and index interfaces
```

### M2 — Implement projection values, ports, and tokenizer

**Work**

- Add immutable segment, filter, hit, index status, and context-scope domain values.
- Add SearchBackend and ProjectionStore ports without importing SQLite into Domain or Application.
- Implement tokenizer v1 and literal query generation.
- Implement deterministic segment construction and canonical locator/citation serialization.
- Implement compatibility metadata and logical snapshot hashing.

**Completion conditions**

- Golden tokenizer cases cover NFKC, case folding, punctuation, mixed Chinese/English, Han single
  characters, adjacent bigrams, extension ranges, and empty queries.
- Repeated segment construction is identical and generated IDs follow ADR-0016.
- No third-party tokenizer, native extension, network access, or global mutable dictionary exists.
- Type checking and focused unit tests pass.

**Git commit:** Yes — P3-C3

```text
feat(search): add deterministic segments and tokenizer
```

### M3 — Implement index-independent grep and get

**Work**

- Implement scanner-backed grep over configured durable roots with stable result sorting and bounds.
- Implement generic object lookup with normalized body, citations, and derived incoming relations.
- Add human and JSON renderers and register `grep` and `get`.

**Completion conditions**

- Both commands work when `kb.sqlite` is absent, corrupt, or incompatible.
- Grep excludes state, config, cache, attachment, and generated files.
- Relative paths and optional durable section IDs are correct; line/column are labeled navigation.
- Missing objects and invalid/empty queries use the frozen diagnostics and exits.

**Git commit:** Yes — P3-C4

```text
feat(cli): add index-independent grep and get
```

### M4 — Implement deterministic rebuild and status

**Work**

- Implement the SQLite projection adapter using bundled DDL v2.
- Implement full snapshot projection, index metadata, integrity checks, sibling staging, and atomic
  replacement.
- Implement read-only status classification and human/JSON output.
- Register `index rebuild` and `index status`.

**Completion conditions**

- Deleting and rebuilding produces equivalent logical rows and stable segment IDs.
- All object kinds, Note roles, citations, relations, tags, type transitions, and scan state project.
- Scanner errors, concurrent changes, lock contention, disk/SQLite failure, and injected interruption
  leave the old database usable and unchanged.
- Missing, fresh, stale, incompatible, and corrupt status paths are directly tested.
- Every installed-wheel rebuild resolves DDL through package resources outside the checkout.

**Git commit:** Yes — P3-C5

```text
feat(index): add deterministic rebuild and status
```

### M5 — Implement incremental build and mutation refresh

**Work**

- Implement checksum/path change sets for object and relation creation, update, delete, and rename.
- Apply changes in one SQLite transaction and refresh affected FTS rows.
- Register `index build`.
- Add best-effort refresh after every successful durable mutation.

**Completion conditions**

- Incremental rows equal a full rebuild for the same final Vault.
- Relation-only changes, no-op builds, deletes, moves, tag changes, role changes, and citation changes
  are covered.
- An absent index stays absent after mutation.
- Refresh failure preserves durable success, emits only the frozen warning, and makes stale state
  observable.

**Git commit:** Yes — P3-C6

```text
feat(index): add incremental projection refresh
```

### M6 — Implement filtered FTS search

**Work**

- Implement FTSBackend with literal query normalization, filters, BM25, and deterministic tie-breaks.
- Apply default active/trusted-local and AI exclusion policy.
- Apply public-safe result eligibility without widening scope.
- Add human and JSON renderers and register `search`.

**Completion conditions**

- Mixed Chinese/English and all filters have command-level evidence.
- Repeated tags use AND, limits are bounded, and raw FTS operators are not executable.
- Missing/stale/incompatible/corrupt indexes fail without mutation.
- Every hit resolves to the expected object, relative path, segment, durable section when present,
  role, and complete ordered citations.
- Default and explicit AI/archive/superseded behavior matches ADR-0016.

**Git commit:** Yes — P3-C7

```text
feat(search): add traceable bilingual fts
```

### M7 — Implement scoped context assembly

**Work**

- Implement deterministic grouping and character-budget assembly over SearchBackend results.
- Implement trusted-local and per-result public-safe policy.
- Add exclusions, citations, truncation metadata, human rendering, and JSON output.
- Register `context` only with required `--scope`.

**Completion conditions**

- Trusted-local can include private eligible content without external transmission.
- Public-safe rejects private, superseded, uncited, incoherent, unreviewed, unsafe-rights, and unsafe
  Snippet dependencies while retaining safe candidates.
- AI content is absent in both Phase 3 context scopes.
- Ordering and budget behavior are deterministic and never cut an item mid-text.
- Output is explicitly not a Phase 6B publish certification.

**Git commit:** Yes — P3-C8

```text
feat(context): add scoped traceable context assembly
```

### M8 — Pass local, package, and isolation gates

**Work**

- Run the complete test suite, Ruff, and mypy.
- Build wheel/sdist and run the distribution audit.
- Install the core wheel outside the source checkout on supported Python versions.
- Exercise DDL loading, rebuild/search/context, package lifecycle, and missing-index behavior from the
  installed artifact.
- Confirm generated SQLite, Vault content, caches, tests, plans, and private data are absent from the
  wheel.

**Completion conditions**

- All local and isolated-install gates are green.
- The installed core package implements Phase 3 without optional Web or Zotero imports.
- Existing Phase 0R through Phase 2B tests remain green.
- CLI help and `CLI.md` contain the same implemented command inventory, but Phase 3 is not marked
  Complete until remote gates pass.

**Git commit:** Yes — P3-C9

```text
test: pass phase 3 local and distribution gates
```

### M9 — Pass remote gates and mark Phase 3 complete

**Work**

- Push only with explicit authorization and wait for Windows, macOS, and Linux × Python 3.13 and
  3.14 CI plus package-smoke success.
- Confirm control of the normalized PyPI project name or the documented fallback before opening
  release gates.
- Set `testpypi-enabled = true` and `pypi-prerelease-enabled = true`; keep
  `pypi-stable-enabled = false`.
- Update README, roadmap, plan README, this goal, and CLI ledger to Complete/Verified with actual
  workflow links.
- Run the status-only completion commit through the same required CI.

**Completion conditions**

- Feature and status commits both have green required CI.
- Every Phase 3 command is `Verified` with command-level and complete-suite evidence.
- Final branch is clean and synchronized.
- No package version, version tag, registry upload, or GitHub Release has been created.

**Git commit:** Yes — P3-C10, only after the first remote feature gate is green

```text
docs: mark phase 3 complete
```

## 6. Explicitly out of scope

- Semantic or hybrid search, embeddings, vector databases, rerankers, or learned retrieval;
- raw caller-controlled FTS5 syntax or regex search as a public contract;
- Web UI, FastAPI, Jinja, Uvicorn, or browser mutation;
- MCP, graph databases, multi-agent memory, or external-model invocation;
- AI review, acceptance, rejection, or promotion commands;
- Snippet creation or extraction;
- full Phase 6B public allowlist closure, staging, Quartz build, or publication certification;
- Git history projection, backlinks, merge, supersession commands, tidy, organize, or review;
- changing Contract v2, configuration v1, transaction v1, or projection DDL v2;
- storing index state outside the configured Vault state directory;
- TestPyPI/PyPI upload, package version change, tag, GitHub Release, merge, or publication without
  separate explicit authorization.

## 7. Checks required before completion

### Function and contract

- All five new interface schemas have valid, invalid, and golden fixtures.
- `kb --version` reports tokenizer independently from parser and projection.
- `grep` and `get` remain fully index-independent.
- Full and incremental projection cover every current v2 object and relation shape.
- Every FTS hit maps to a permanent object ID, relative path, projection segment, and durable Note
  section when applicable.
- Query filters, default limits, tag AND semantics, ranking, tie-breaks, and literal escaping match the
  frozen interface.
- Context grouping, citations, exclusions, and character budget are deterministic.

### Determinism, conflict, and atomicity

- Two rebuilds from identical durable bytes have equivalent logical rows and stable segment IDs.
- Incremental build equals full rebuild for the same final snapshot.
- Parser, tokenizer, segment, projection, or Contract version mismatch requires rebuild.
- File changes between scan and commit produce `INDEX_SOURCE_CHANGED` without replacing the index.
- Lock contention, process interruption, disk failure, malformed DDL, and SQLite integrity failure
  preserve the last successful database.
- No-op build does not rewrite content rows.
- Durable mutation remains successful when best-effort refresh fails.

### Search, privacy, and public-safe behavior

- Default search includes eligible active local Source/human/fact/snippet content and excludes AI,
  archived, and superseded results.
- Explicit AI search is trusted-local only and promoted Note AI rules remain enforced.
- Source-free human content has human provenance and empty citations.
- Every Fact result retains all citations and exact locator provenance.
- Public-safe context excludes private, unresolved, superseded, uncited, incoherent, unreviewed, and
  unresolved-rights dependencies with stable reasons.
- Absolute paths, SQL text, private excerpts in diagnostics, and raw Artifact bodies never escape.
- Public-safe context is not represented as a publish audit or manifest.

### Packaging and compatibility

- Core wheel remains pure Python and adds no tokenizer dependency.
- SQLite FTS5 capability is verified on every supported OS/Python job with a typed failure if absent.
- Bundled DDL and interface schema bytes match top-level authority.
- Wheel excludes databases, journals, Vault files, generated context, tests, plans, caches, and logs.
- Installed commands work outside the source checkout.
- Install, upgrade, downgrade, and uninstall do not mutate a Vault.
- Missing Web/Zotero extras do not break Phase 3 core commands.

### Required local commands

```powershell
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests scripts
uv run --no-sync mypy src tests scripts
uv build
uv run --no-sync python scripts/verify_distribution.py dist
```

Repository-provided isolated-install and lifecycle checks must also pass. GitHub Actions must cover:

- Windows, macOS, and Linux;
- Python 3.13 and 3.14;
- complete tests, Ruff, and mypy;
- wheel/sdist build and audit;
- installed DDL, rebuild, search, context, and lifecycle behavior.

Phase 3 is Complete only after the status-only completion commit passes required CI and the release
gate prerequisites are documented. Actual publication remains separately authorized.

## 8. Git execution rules

- Milestone commits are required rollback checkpoints, but every Git mutation requires explicit user
  authorization.
- Each commit contains only its milestone and excludes generated databases, build artifacts, Vaults,
  caches, and unrelated work.
- Do not push a command marked Verified before its command-level and complete-suite evidence exists.
- Push, PR, merge, tag, package version change, TestPyPI, PyPI, and GitHub Release are separate
  permissions.
- Do not open release gates or mark Phase 3 Complete before the required feature CI is green and
  project-name control is proven.
- A green Phase 3 gate does not authorize publishing.
