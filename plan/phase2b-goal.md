# Phase 2B execution goal: Unified Source capture

> **Status:** Complete — local, distribution, isolated-install, and supported-platform feature gates
> are green; the status-only completion commit must pass the same required CI before handoff
> **Target branch:** `Phase2B`
> **Implementation baseline commit:** `85aa27acaa34626be74eafc9b04a24ed78d5c3fd`
> **Baseline state:** branch tracks `origin/Phase2B`; commit and push were explicitly authorized

## 1. Current foundation and authority

Phase 0R, Phase 1, and Phase 2A are complete. Phase 2B directly reuses:

- Contract v2 Source, Snippet, Locator, and Relation models;
- Phase 1 Vault discovery, scanner, atomic writes, conflict detection, and recoverable transactions;
- the verified `kb note new --type literature --source SOURCE_ID` workflow and its atomic
  `summarizes` relation;
- Phase 2A DOI/arXiv normalization, injectable Paper metadata port, internal Paper capture service,
  exact-reference read-only Zotero Local API adapter, attachment integrity checks, Source queries,
  and Paper synchronization; production DOI/arXiv candidate search remains Phase 2B work;
- the existing `add-result-v1` JSON contract and unified CLI error/envelope framework;
- wheel resource packaging, isolated installation, and cross-platform CI.

This goal is subordinate to the machine contracts and follows:

- [`roadmap.md`](roadmap.md);
- [`ADR-0009`](decisions/0009-unified-add-command.md);
- [`ADR-0013`](decisions/0013-phase2b-project-level-oss-and-deferred-snippets.md);
- [`ADR-0014`](decisions/0014-phase2a-acceptance-and-phase2b-zotero-classification.md);
- [`ADR-0015`](decisions/0015-phase2b-provenance-and-anonymous-git.md);
- [`interfaces.md`](interfaces.md);
- [`data-model.md`](data-model.md);
- [`sources-and-adapters.md`](sources-and-adapters.md);
- [`security-publishing.md`](security-publishing.md);
- the current Contract v2 and configuration v1 schemas.

Implementation extends the existing Python CLI, Domain, Port, Adapter, and Vault boundaries. It
must not introduce a parallel architecture.

## 2. Final outcome

After Phase 2B is complete, Knowlume provides one public capture command:

```text
kb add INPUT [--type paper|web|book|repo] [--json]
```

All four Source paths are released together:

- Paper: DOI and arXiv;
- Web: HTTP(S) URL backed by an exact Zotero HTML/XHTML snapshot;
- Book: checksum-valid ISBN, DOI, and exact Zotero Book metadata;
- OSS: an HTTP(S) repository-root URL resolved to the current immutable remote HEAD commit.

The user can override recognition with `--type`, but the override cannot bypass metadata,
snapshot, repository-root, Schema, or security validation. Repeating the same canonical identity
returns the existing Source ID with `created: false`.

Web Sources preserve a recoverable Zotero snapshot reference, attachment capture time, and SHA-256
without storing webpage content in the Vault. Book Sources preserve normalized ISBN/DOI and edition
information. OSS Sources preserve project host, complete project path, default branch, full commit,
and `license: NOASSERTION`; no repository content is cloned or read.

An overall open-source project note uses the existing Literature Note workflow:

```text
kb add REPOSITORY_URL --type repo --json
kb note new --type literature --source SOURCE_ID
```

The second command explicitly creates the Note and its `summarizes` relation. Phase 2B does not add
a Project Note type and does not automatically create a Note during Source capture.

Contract v2 Snippet documents remain readable and valid. No Snippet creation service or command is
implemented. `kb snippet add` is indefinitely deferred with no assigned roadmap phase.

## 3. Frozen interfaces and behavior

### 3.1 Recognition order

Recognition must follow this exact order:

1. explicit `--type`;
2. arXiv identifier or URL;
3. DOI, classified as Paper or Book by exact Zotero metadata;
4. checksum-valid ISBN;
5. repository-root URL on a known or configured Git host;
6. another HTTP(S) URL.

If a DOI cannot be classified as Paper or Book, return `ADD_TYPE_AMBIGUOUS`; never guess. An
unknown self-hosted Git host defaults to Web unless configured or explicitly selected with
`--type repo`. Explicit repo selection still requires successful project-root and remote-HEAD
resolution.

Explicit override shapes are fixed:

| `--type` | Accepted input | Incompatible input |
|---|---|---|
| `paper` | DOI or arXiv identifier/URL | `ADD_INPUT_INVALID` (2) |
| `book` | DOI or checksum-valid ISBN | `ADD_INPUT_INVALID` (2) |
| `web` | credential-free HTTP(S) URL | `ADD_INPUT_INVALID` (2) |
| `repo` | credential-free HTTP(S) repository-root candidate | `ADD_INPUT_INVALID` (2) |

For an automatic DOI, zero, multiple, mixed-type, or unsupported exact Zotero candidates return
`ADD_TYPE_AMBIGUOUS`. With explicit `--type paper` or `--type book`, zero, multiple, or
type-incompatible exact candidates return `ADD_METADATA_UNAVAILABLE`. An override never converts an
ineligible Zotero item into eligible metadata.

### 3.2 Canonical identities

- Paper: prefer `doi:<normalized-doi>`; otherwise `arxiv:<base-id>`.
- Book: prefer canonical ISBN-13 as `isbn:<isbn13>`; otherwise
  `doi:<normalized-doi>`.
- Web: `url:<canonical-url>`.
- OSS: `repo:<host>/<project-path>@<full-commit>`.
- Source ID is the permanent domain identity. External identities are lookup and recovery keys.
- DOI/arXiv or DOI/ISBN aliases that resolve to different Source IDs are blocking conflicts and
  are never merged automatically.

Web URL canonicalization must at least lowercase scheme and IDNA host, remove default ports and
fragments, normalize an empty path and dot segments, and decode unambiguous unreserved
percent-encoded characters. It preserves path case, trailing slash, query ordering, and query
values.

Repository normalization accepts only HTTP(S), lowercases and IDNA-normalizes the host, removes a
default port, removes one trailing slash and one terminal `.git`, and preserves project-path case.
Credentials, query strings, fragments, empty project names, and non-root provider routes are
invalid. Canonical URL, repository host/path, and identity must be derived from the same normalized
value.

Configured repository hosts extend the built-in `github.com` and `gitlab.com` set. A missing section
or empty configured list keeps those defaults. Configuration accepts bare DNS hostnames only,
normalizes them to lowercase IDNA A-labels after removing one terminal root-domain dot, rejects
scheme, credentials, port, path, wildcard, IP literal, `localhost`, whitespace, empty values, and
normalized duplicates, and matches the complete hostname without subdomain inheritance.

### 3.3 Zotero scope

- Use only Zotero's supported read-only Local API; never read `zotero.sqlite`.
- Automatic search is limited to the personal `users/0` library. Existing exact group-library
  references remain readable, but unified capture does not enumerate groups.
- Zotero quick search only narrows candidates. Returned candidates are normalized again and matched
  exactly by DOI, arXiv, ISBN, or URL.
- Zero or multiple exact candidates fail. Never choose the first item.
- New Paper capture accepts only top-level Zotero `journalArticle`, `conferencePaper`, `preprint`,
  `thesis`, `report`, and `manuscript` items.
- Book accepts only a top-level Zotero `book`; `bookSection`, missing `itemType`, and every other type
  are out of scope.
- Existing exact-reference Phase 2A Paper Sources remain readable and synchronizable without
  retroactive item-type classification.
- Zotero HTTP remains in the `zotero` extra and must not be imported eagerly by the core wheel.

Implementation follows the official [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)
and [Zotero API basics](https://www.zotero.org/support/dev/web_api/v3/basics).

### 3.4 Web snapshot

- Match one exact Zotero top-level `webpage` item and exactly one recoverable child snapshot whose
  `itemType` is `attachment`, `parentItem` matches the webpage item key, `linkMode` is
  `imported_url`, and `contentType` is `text/html` or `application/xhtml+xml`.
- `snapshot_ref.provider` is `zotero`.
- `snapshot_ref.identifier` is:

  ```text
  user/0/<parent-item-key>/<attachment-key>
  ```

- Source `captured_at` and `snapshot_ref.captured_at` are identical and come from attachment
  `dateAdded`. Missing or malformed values fail; current time is never substituted.
- SHA-256 is calculated from the recovered attachment bytes.
- Empty attachment bytes are ineligible.
- Zero or multiple eligible snapshots return metadata-unavailable and write nothing.
- Snapshot bytes are used only to calculate integrity evidence; they are not persisted in the
  Vault.
- Repeating a canonical Web URL returns the first accepted Source and does not refresh or replace
  its snapshot in Phase 2B.
- Existing v2 Web Sources without `snapshot_ref` remain readable, scannable, listable, and showable;
  Schema does not make the field globally required and there is no migration or rewrite.
- A Web Locator exactly matches the Source snapshot provider, identifier, capture time, and SHA-256.
  An old Source without coherent snapshot evidence cannot support a new Web citation or pass public
  dependency closure until repaired by a future reviewed workflow.

### 3.5 Book and edition

Contract v2 Source gains one backward-compatible optional `edition` field:

- it is valid only for Book Sources;
- it is a non-empty, trimmed string;
- ISBN-10 is checksum-validated and converted to ISBN-13;
- a newly captured Book has at least a valid ISBN or DOI;
- a DOI-only Book can be captured, but a page Locator remains invalid until an edition or ISBN is
  present;
- existing v2 files remain valid and require no automatic migration.

ISBN comparison uses canonical ISBN-13. Edition comparison uses the complete case-sensitive string
after trimming outer whitespace. A Book page Locator carries at least one ISBN or edition already
present on the Source; every value it carries must match, and it cannot introduce evidence absent
from the Source. If the Source has both values, the Locator may carry one, but both must match when
both are present. Fact and relation validation reuse `FACT_LOCATOR_MISMATCH` and
`RELATION_LOCATOR_MISMATCH` with mismatched-field details.

Book capture maps title, authors, year, ISBN, DOI, edition, canonical URL when present, and Zotero
recovery fields. Phase 2B does not extend `source sync` to Books.

### 3.6 Project-level OSS Source

Configuration v1 gains one optional section without changing `config_version = 1`:

```toml
[capture]
repository_hosts = ["github.com", "gitlab.com"]
```

Rules:

- absence of the section or an empty list defaults to `github.com` and `gitlab.com`; configured hosts
  extend rather than replace this set;
- host values are unique normalized bare DNS hostnames without scheme, port, path, credentials,
  wildcard, IP literal, `localhost`, or whitespace;
- host normalization lowercases, applies IDNA A-label conversion, removes one terminal root-domain
  dot, and rejects duplicates after normalization;
- matching uses the complete hostname and does not inherit configured permission to subdomains;
- configured self-hosted Git hosts and nested GitLab-style groups are recognized automatically;
- explicit `--type repo` may select another self-hosted HTTP(S) Git server, but still requires a
  generic root-shaped path and successful remote-HEAD resolution;
- public input is an HTTP(S) repository-root URL only;
- GitHub roots contain exactly two path segments. GitLab and configured hosts accept nested project
  paths with at least two segments. GitHub `/blob/` and `/tree/` routes and GitLab `/-/` routes are
  rejected;
- credentials, queries, fragments, file/subdirectory paths, local paths, SCP syntax, and explicit
  revision input are rejected;
- use read-only remote-reference discovery, such as `git ls-remote --symref URL HEAD`, to obtain the
  default branch and a 40- or 64-character lowercase full commit;
- use disposable isolated Git configuration and a rejecting platform askpass helper; disable terminal
  and GUI prompts, credential helpers, interactive credential managers, and system/global URL
  rewrites;
- unavailable Git, authentication requirements, inaccessible repositories, malformed refs,
  symbolic-ref loops, and unborn HEAD return typed capability/metadata failures without exposing
  commands, task-local paths, environment values, or remote stderr;
- title defaults deterministically to the final repository path component after removing `.git`;
- the Source records canonical URL, repository host, full project path, default branch, commit, and
  `license: NOASSERTION`;
- do not clone, fetch repository bodies, inspect license files, infer SPDX identifiers, or write
  license evidence;
- an unchanged remote HEAD returns the existing Source; a later HEAD commit creates a distinct
  immutable Source.
- any OSS Locator exactly matches the Source normalized host, complete project path, and full commit;
  Fact and relation mismatches reuse the existing locator-mismatch findings.
- tests use an injectable command runner and platform-native fake Git executable and never contact a
  public repository.

The mutable repository URL is an intake route. The full commit, not the branch or live URL alone,
is the durable provenance identity.

### 3.7 Overall project note

- Repo capture writes only an OSS Source.
- `kb note new --type literature --source SOURCE_ID` accepts the captured OSS Source through the
  already implemented generic Literature Note workflow.
- Note creation remains explicit and atomic with the required `summarizes` relation.
- The Note is private by default and contains at least one human section.
- No new object kind, Note type, relation type, or machine-output schema is introduced.
- Integration tests must prove the two-command workflow without duplicating Phase 1 Note logic.

### 3.8 Snippet compatibility boundary

- Existing Contract v2 Snippet schema, template, fixtures, parsing, migration, relation validation,
  and publication checks remain unchanged and readable.
- Phase 2B adds no Snippet fields, license-evidence fields, creator, writer, Git-content reader, or
  CLI group.
- `kb snippet add` must not appear in registered help.
- Snippet creation is not reassigned to Phase 3–7 and has no delivery date.
- A future implementation requires a new accepted ADR that validates the use case and freezes
  syntax, content recovery, path/submodule safety, line ranges, license evidence, publication
  approval, idempotency, and recoverable multi-file writes.

## 4. Requirements that cannot be omitted

- Release all four `kb add` backends together; do not expose a partial parent command.
- Durable changes follow ADR -> Schema -> Template -> Fixture -> contract test -> production code.
- Do not change historical v1 schemas, templates, or fixtures.
- Preserve the successful `add-result-v1` fields exactly:
  - `input`;
  - `requested_type`;
  - `detected_type`;
  - `source_type`;
  - `canonical_identity`;
  - `source_id`;
  - `created`.
- CLI type `repo` maps to durable `source_type: oss`.
- Preserve principal diagnostics and exits:
  - `ADD_INPUT_INVALID` -> 2;
  - `ADD_TYPE_AMBIGUOUS` -> 3;
  - `ADD_IDENTITY_CONFLICT` -> 3;
  - `ADD_METADATA_UNAVAILABLE` -> 5;
  - `ADD_WRITE_CONFLICT` -> 4.
- Recognition, Zotero, snapshot, Git-ref, Schema, scan, conflict, and interruption failures leave no
  partial Source or transaction state.
- All new Sources and Notes default to private.
- Never write absolute paths, credentials, tokens, webpage/attachment bodies, Zotero storage paths,
  repository bodies, clones, caches, or logs into the Vault.
- Mutable Web material requires snapshot reference, capture time, and hash.
- OSS provenance requires a full immutable commit; branch name is display metadata only.
- Project-level OSS capture always records `license: NOASSERTION` and makes no legal inference.
- Publishing continues to fail closed for unresolved rights, private dependencies, incomplete Fact
  citations, unsafe paths, unreviewed AI, and existing unapproved Snippets.
- Keep `CLI.md` synchronized with command phase and status. Mark `Verified` only after command-level
  evidence, the complete local gate, and supported CI pass.
- Top-level Schema/Template files and wheel resources remain byte-identical.
- The `web` extra remains reserved for Phase 4 Web UI; Web capture uses the `zotero` extra.
- The core wheel must import and show help without HTTPX or optional Zotero dependencies.
- Never access Zotero private databases or write endpoints.
- Do not expand Phase 2A `source sync` behavior to Web, Book, or OSS in this phase.
- Do not register or implement `kb snippet add`.

## 5. Milestones and work steps

Every milestone must pass its own checks before its checkpoint commit. The commit entries are
execution requirements, but this document does not itself authorize stage, commit, push, PR, merge,
tag, or release operations.

### M0 — Freeze the revised Phase 2B decision — Complete

**Requirements**

- Accept ADR-0013.
- Synchronize roadmap, interfaces, data model, source/adapter, security/publishing, CLI ledger,
  navigation, and this execution goal.
- Explicitly retain Snippet read compatibility while removing creation from every scheduled phase.
- Explicitly select Literature Note for overall project notes.

**Limits**

- No production-code, Schema, template, or fixture changes.
- Do not register `kb add` or any Snippet command.

**Completion conditions**

- Authority documents contain no Snippet-delivery or license-inspection promise in Phase 2B.
- OSS identity, remote-HEAD behavior, note handoff, and refresh boundaries have no open decision.
- Internal documentation links and whitespace checks pass.

**Completed checkpoint:** P2B-C1 at `59988c3694cda5b028fbd4ffd8d1ad2323b86f06`

```text
项目级 OSS Source，复用 Literature Note 做整体项目笔记，并把 Snippet 创建能力无期限延期
```

### M0A — Reconcile Phase 2A acceptance evidence — Complete

**Requirements**

- Accept ADR-0014 and link ADR-0012/0013 to its clarification without rewriting their historical
  decisions.
- Correct the Phase 2A goal so it claims an injectable metadata port and exact-reference Zotero
  adapter, not a production DOI/arXiv candidate-search resolver.
- Keep Phase 2A Complete/Verified and record an explicit acceptance erratum; do not move the
  `Phase2A` tag or rewrite history.
- Freeze every Phase 2A Source-command error/warning and exit or warning severity in
  `interfaces.md`; reference shared Phase 1 diagnostics instead of duplicating them.
- Add direct CLI evidence for all four `source list` filters, successful and failed `source open`,
  `source sync --adopt-remote`, `source sync --accept-attachment-change`, warning envelopes, and
  principal human-readable Source/workflow output.

**Limits**

- This checkpoint changes decisions, active documentation, CLI tests, and test fixtures only.
- Do not change production code unless a new command-level test exposes a real wiring defect.
- If a production defect is exposed, fix it in a separate P2B-C1B checkpoint and rerun M0A.
- Do not change object/config Schemas, register `kb add`, or begin a Phase 2B backend.

**Completion conditions**

- The Phase 2A completion wording matches the executable dependency-injection and exact-reference
  paths.
- Every registered Phase 2A Source option has direct command-level evidence.
- Human and JSON errors use the same frozen exit code; warnings have direct human and JSON evidence.
- Targeted Phase 2A tests, the complete repository suite, Ruff, and mypy pass.

**Completed checkpoint:** P2B-C1A at `49a4615293739795e2be78ca1b70f9928848d7f2`

```text
test(phase2a): reconcile capture and CLI acceptance evidence
```

### M0B — Freeze provenance coherence and anonymous Git policy — Complete

**Requirements**

- Accept ADR-0015 and link ADR-0013/0014 to its clarification without rewriting their historical
  decisions.
- Synchronize the data model, source/adapter, interface, security/publishing, roadmap, navigation,
  and this execution goal.
- Freeze the Web new-capture versus old-v2 compatibility boundary, Book/OSS Source–Locator
  coherence, configured-host normalization and exact matching, anonymous Git isolation, and offline
  installed-wheel test policy.
- Keep Contract v2 and configuration v1 version numbers unchanged and record that no migration is
  triggered.

**Limits**

- Documentation and accepted decisions only; no Schema, template, fixture, production-code, or CLI
  registration changes.
- Do not reopen Phase 2A, move its tag, begin M1, or alter Snippet scope.
- P2B-C1B remains reserved for a production defect exposed by M0A and is not reused.

**Completion conditions**

- Every new Web snapshot eligibility field and legacy compatibility consequence is explicit.
- Book and OSS Locator equality rules have no implementation choice left open.
- Host defaults, extension, normalization, exact matching, and invalid forms are deterministic.
- Git cannot use ambient credentials or URL rewrites, and all Git tests are offline.
- Internal documentation links, the complete repository suite, Ruff, and mypy pass.

**Completed checkpoint:** P2B-C1C

```text
docs(contract): freeze phase 2b provenance and git policy
```

### M1 — Extend current contracts and configuration

**Requirements**

- Add optional Source `edition` to the authoritative Contract v2 Schema, domain model, parser, and
  renderer.
- Add optional configuration v1 `[capture].repository_hosts` to Schema, configuration model, parser,
  and renderer while preserving default hosts.
- Update current Source/config templates and bundled resource inputs where applicable.
- Add valid and invalid Book edition and repository-host configuration fixtures.
- Add source-specific Locator coherence fixtures/tests needed by Book, Web, and OSS capture.
- Keep `snapshot_ref` optional in the global Web Source Schema while enforcing complete evidence for
  new capture and affected citations in application/domain semantics.
- Extend existing Fact/relation locator-mismatch findings with mismatched-field details; do not add a
  parallel finding vocabulary.
- Establish failing contract/parser tests before production parsing changes.

**Limits**

- Do not add `license_evidence`.
- Do not modify Snippet schemas, templates, fixtures, or parsing behavior.
- Existing Contract v2 and config v1 files remain valid; no automatic migration.
- Historical v1 object/template/fixture directories remain read-only.

**Completion conditions**

- Old and new valid fixtures pass.
- Edition type/source restrictions, whitespace boundaries, page-locator ISBN/edition requirements,
  Source/Locator mismatches, duplicate/invalid/wildcard repository hosts, and unsafe host forms have
  negative evidence.
- Old Web Sources without snapshots remain readable; new Web capture cannot produce one.
- Config without `[capture]` and config with an empty host list resolve the default host set
  deterministically; configured hosts extend defaults and do not authorize subdomains.
- Bundled assets match top-level authorities byte for byte.

**Git commit:** Yes — P2B-C2

```text
feat(contract): add book edition and repository host config
```

### M2 — Implement pure recognition candidates and normalization

**Requirements**

- Add one pure recognizer, normalized input values, capture candidate types, and capture backend
  ports.
- Implement DOI, arXiv, ISBN-10/13, Web URL, and repository-root normalization.
- Enforce the frozen recognition order and all explicit `--type` combinations.
- Convert valid ISBN-10 to canonical ISBN-13.
- Recognize default and configured repository hosts automatically; permit an explicit repo override
  for another HTTP(S) host only when generic root and later adapter validation can succeed.
- Apply exact complete-host matching after lowercase IDNA normalization and terminal-dot removal;
  never infer configured subdomains.
- Output the raw input, explicit requested type, normalized input kind, and the unresolved candidate
  required by the next adapter boundary.
- Keep DOI as a DOI candidate until Zotero classification; keep repo as a normalized repo candidate
  until remote HEAD is resolved.
- Produce canonical URL, ISBN, and arXiv values when they are derivable without external I/O.

**Limits**

- This layer performs no Zotero, network, Git, or Vault I/O.
- This layer does not produce final DOI Paper/Book classification, commit-qualified repo identity,
  Source ID, `created`, or a complete `add-result-v1` success object.
- Do not infer a type from title text, URL keywords outside frozen provider routes, or result order.
- Do not accept local repository paths, SSH/SCP URLs, or revision syntax.

**Completion conditions**

- Four candidate paths, every override shape, invalid ISBN, credential-bearing URL, unknown host
  defaulting to Web, explicit unknown-host repo selection, known non-root repo URL, and URL
  canonicalization goldens pass.
- Repository-host goldens cover built-in extension, empty config, IDNA/case/terminal-dot equivalence,
  exact subdomain rejection, GitHub two-segment roots, and nested GitLab/configured paths.
- Equivalent accepted input produces one normalized candidate; invalid forms fail deterministically.
- CLI `repo` is represented internally as durable `oss`.

**Git commit:** Yes — P2B-C3

```text
feat(capture): add unified recognition and canonical identities
```

### M3 — Implement Zotero search, classification, and capture metadata resolution

**Requirements**

- Implement read-only top-level item search in personal library `users/0`.
- Follow pagination to enumerate the complete quick-search candidate set, then re-normalize and
  exactly match all candidates.
- Implement the production `PaperMetadataPort` for DOI/arXiv capture using that exact candidate
  search.
- Reuse Phase 2A DOI/arXiv normalization, Paper Source construction, primary-PDF integrity, and
  exact-reference item mapping; do not claim that Phase 2A already supplied candidate search.
- Before mapping a new Source, accept only the ADR-0014 Paper whitelist or top-level `book` and reject
  missing/unsupported types without guessing.
- Map top-level Book metadata including ISBN, DOI, edition, and recovery reference.
- Select exactly one top-level `webpage` and one child `imported_url` HTML/XHTML attachment with
  matching parent, parseable `dateAdded`, and non-empty recoverable bytes; recover bytes transiently
  and calculate SHA-256.
- Translate unavailable service, timeout, permission, missing item/attachment, malformed response,
  and missing optional dependency into typed capability/metadata failures.

**Limits**

- No Zotero Cloud API, group-library search, write request, or private SQLite access.
- No snapshot or attachment body in durable files.
- Do not make `snapshot_ref` globally required for old v2 Web Sources or retroactively invalidate
  their read/list/show behavior.
- No `bookSection` support.
- Do not extend `source sync` to Web or Book.
- Do not apply the new item-type whitelist retroactively to exact-reference synchronization of an
  existing Phase 2A Paper Source.

**Completion conditions**

- Zero, one, and multiple exact item candidates have tests.
- Automatic DOI tests cover all six Paper types, top-level `book`, mixed Paper/Book candidates,
  `bookSection`, unknown type, and missing `itemType`.
- Explicit Paper/Book tests cover missing, multiple, and type-incompatible candidates plus absent
  adapter capability.
- Zero, one, and multiple eligible Web snapshots have tests, including wrong `itemType`, parent,
  `linkMode`, and MIME type.
- Missing/malformed `dateAdded`, empty/unrecoverable attachment bytes, timeouts, missing HTTPX, and
  malformed payloads fail without writes.
- New Source and snapshot capture times are equal; Web Locator provider, identifier, capture time, and
  hash coherence has positive and field-by-field negative evidence.
- Paper Phase 2A capture, open, and sync behavior has no regression.

**Git commit:** Yes — P2B-C4

```text
feat(zotero): resolve paper book and web capture metadata
```

### M4 — Implement project-level OSS remote resolution

**Requirements**

- Resolve GitHub, GitLab, configured self-hosted hosts, and nested group project roots.
- Use a narrow Git command port and adapter to discover symbolic default HEAD and its full commit.
- Use disposable isolated Git configuration and a rejecting askpass helper; disable terminal/GUI
  prompts, credential helpers, interactive credential managers, and system/global URL rewrites.
- Sanitize typed failures so command details, task-local paths, environment values, and remote stderr
  cannot reach durable files or the public envelope.
- Construct metadata only from normalized URL and remote refs: deterministic title, canonical URL,
  host, project path, default branch, full commit, and `license: NOASSERTION`.
- Keep the command runner injectable so tests do not depend on the public internet.

**Limits**

- No clone, checkout, fetch of repository bodies, object database, file read, code analysis, or
  license inspection.
- No arbitrary commit/branch/tag input and no branch name in canonical identity.
- Do not persist command lines containing secrets, local paths, remote output, or environment data.
- Do not use ambient system/global Git configuration, credential helpers, askpass success paths, or
  authenticated remotes.
- Monorepo subdirectories are not separate repo Sources.

**Completion conditions**

- GitHub, nested GitLab, configured host, exact subdomain handling, `.git`/trailing-slash
  normalization, and default HEAD pass.
- SHA-1 and SHA-256 full object IDs are accepted; abbreviated/mixed-case/invalid IDs fail.
- Detached/malformed/unborn HEAD, missing Git, prompt-required authentication, timeout,
  inaccessible repository, and ambiguous project root produce typed failures.
- Unit and application tests use an injectable command fake. Installed-wheel smoke injects an
  executable `git` shim on POSIX and `git.cmd` on Windows through temporary `PATH`; no test requires
  a public network.
- Tests assert the exact permitted argv/environment policy and cover success, missing Git, nonzero
  exit, malformed response, authentication requirement, and redaction.
- Tests prove that the adapter never invokes clone, checkout, fetch, show, cat-file, or file reads.

**Git commit:** Yes — P2B-C5

```text
feat(capture): add project-level repository resolver
```

### M5 — Complete all four capture services and atomic writes

**Requirements**

- Compose recognition, metadata resolution, identity index, Source construction, adapters, and
  Vault writes in one unified application service.
- Form final `detected_type`, durable `source_type`, canonical identity, Source ID, and
  `add-result-v1` only after the candidate's required metadata or remote resolution succeeds.
- For identities derivable before adapter access, look up duplicates before unnecessary external
  work. Repo capture first resolves HEAD because commit is part of identity.
- Converge DOI/arXiv and DOI/ISBN aliases on one Source; translate split aliases and cross-Paper/Book
  DOI collisions to `ADD_IDENTITY_CONFLICT` rather than a write conflict.
- Create Web, Book, and OSS Sources in their existing v2 locations through current templates.
- Freeze the first Web snapshot for a canonical URL.
- Validate Book, Web, and OSS Source–Locator coherence before transaction commit whenever the
  capture operation creates or validates affected durable dependencies.
- Run a complete scan after every write and roll back on scan failure.
- Reuse expected-checksum conflicts and recoverable transaction behavior.

**Limits**

- Keep public `kb add` unregistered until every backend passes.
- Do not depend on Phase 3 SQLite projection or search.
- Do not write Notes, Snippets, or relations during `kb add`.

**Completion conditions**

- Paper, Web, Book, and OSS pass creation, repeat capture, identity conflict, target conflict, scan
  failure, and interruption recovery.
- Repeated repo capture with unchanged HEAD returns the same ID; changed HEAD creates a different
  Source.
- Every failure leaves the Vault byte-identical and transaction/lock state recoverable and clean.
- Legacy Web Sources without snapshots remain readable, while attempts to use them as new/public Web
  citations fail closed without durable changes.
- The same unified service invokes all four backends and returns one result type.
- An explicit override produces equal `requested_type` and `detected_type`; automatic capture records
  the final adapter-resolved type.

**Git commit:** Yes — P2B-C6

```text
feat(capture): complete phase 2b source capture services
```

### M6 — Verify the OSS Source to Literature Note workflow

**Requirements**

- Add integration evidence for repo capture followed by
  `kb note new --type literature --source SOURCE_ID`.
- Prove the Note uses its existing v2 Literature shape and atomically creates one `summarizes`
  relation to the captured OSS Source.
- Prove Source capture alone creates no Note or relation.
- Keep existing Note command behavior and help unchanged.

**Limits**

- Do not introduce Project Note, new relation types, automatic Note creation, or OSS-specific Note
  fields.
- Do not duplicate Phase 1 Note service logic.

**Completion conditions**

- The two-command project-note workflow passes application and CLI-level tests.
- Wrong/missing Source ID still follows existing Note diagnostics and leaves no partial Note/relation.
- New Note and Source remain private by default.

**Git commit:** Yes — P2B-C7

```text
test(capture): verify oss literature note workflow
```

### M7 — Register the public unified CLI

**Requirements**

- Register `kb add` only after all four backend and integration gates pass.
- Implement human-readable output, `--json`, add-result goldens, typed errors, and fixed exits.
- Translate adapter construction, Zotero/Git transport, response, scan, and invariant failures into
  the stable `ADD_*` vocabulary; do not expose internal adapter codes through `kb add`.
- Use `ADD_IDENTITY_CONFLICT` (3) for semantic alias collisions and reserve
  `ADD_WRITE_CONFLICT` (4) for concurrent durable changes.
- Ensure expected failures have no traceback and do not expose debug data, paths, credentials, or
  remote command details.
- Update `CLI.md` to `Implemented`; do not mark `Verified` yet.
- Confirm no `snippet` command or help group is registered.

**Limits**

- Do not expose separate `kb add paper/web/book/repo` public subcommands.
- `--type` only selects recognition; it cannot bypass adapter or security validation.
- Do not expand existing Source commands.

**Completion conditions**

- Four CLI paths, all overrides, duplicate capture, changed repo HEAD, JSON goldens, every stable
  `ADD_*` exit, help text, and stdout/stderr separation pass.
- Human and JSON modes map the same failure to the same exit code; warning envelopes have golden
  evidence.
- Core-only wheel help and repo path load without Zotero dependencies.
- Paper, Book, and Web return typed capability failure when the Zotero extra is absent.
- `kb snippet` remains absent.

**Git commit:** Yes — P2B-C8

```text
feat(cli): expose phase 2b unified source capture
```

### M8 — Pass local, package, and isolation gates

**Requirements**

- Run the complete tests, Ruff, mypy, build, and distribution audit.
- Keep the Phase 2A M0A command-level acceptance suite in the complete regression gate.
- Extend wheel smoke for `kb add --help`, an offline platform-native fake-Git repo fixture, absent
  `kb snippet`, and missing Zotero-extra behavior.
- Verify Paper, Book, and Web adapter wiring in an isolated `knowlume[zotero]` environment.
- Run installed CLI checks outside the source checkout.
- Record local evidence without declaring Phase 2B Complete.

**Limits**

- No TestPyPI, PyPI, GitHub Release, tag, automatic push, or automatic PR.
- Generated distributions and temporary environments are not committed.
- Local evidence cannot substitute for supported-platform CI.

**Completion conditions**

- Every local check in section 7 passes.
- Distribution contents and bundled assets pass audit.
- Installed repo smoke proves Git argv/environment isolation, error redaction, and absence of public
  network access on Windows and POSIX runners.
- Git diff contains no generated, private, absolute-path, or unrelated content.
- The checkpoint commit leaves a clean working tree.

**Git commit:** Yes — P2B-C9

```text
test: pass phase 2b local and distribution gates
```

**Local evidence recorded 2026-08-29 (uncommitted working tree):** the complete pytest gate passes
with 397 passed and 3 skipped, and Ruff and mypy pass; wheel/sdist build and distribution audit pass;
core-only and Zotero-extra isolated installation smoke passes outside the checkout with an offline
platform-native fake Git command that checks the permitted arguments/environment and redacted
failure paths; the package lifecycle smoke confirms install, upgrade, downgrade, and uninstall do
not mutate a Vault. This evidence does not replace the required checkpoint commits or M9
supported-platform CI.

### M9 — Pass remote CI and mark Phase 2B complete

**Feature-gate evidence:** commit `6c419fcafc2dece59db5793f6ee792e22f283625` passed
[CI](https://github.com/yjdy/Knowlume/actions/runs/33252123661) and
[package smoke](https://github.com/yjdy/Knowlume/actions/runs/33252123610) on the required platform and
Python matrix. P2B-C10 records the completion status; its own required workflows remain the final
handoff gate.

**Requirements**

- Obtain explicit user authorization before push or PR creation.
- Push the reviewed checkpoint branch and run GitHub Actions on Windows, macOS, and Linux with
  Python 3.13 and 3.14.
- Resolve every CI failure with a scoped change and rerun the affected local gates.
- Only after remote CI is green, update README, roadmap, and `CLI.md` to Complete/Verified and record
  exact evidence links.
- Push the status-only commit and require its CI to pass as well.

**Limits**

- Do not merge, tag, or publish a package without separate explicit authorization.
- Do not conceal, skip, or weaken a failing contract, security, package, or platform check.

**Completion conditions**

- Feature and status commits both have green required CI.
- `kb add` is `Verified`; `snippet.add` remains `Deferred` and unregistered.
- Final branch is clean and Phase 2B completion claims link to actual CI evidence.

**Git commit:** Yes — P2B-C10, only after the first remote CI gate is green

```text
docs: mark phase 2b complete
```

## 6. Explicitly out of scope

- Snippet creation, extraction, editing, approval, or CLI registration, indefinitely;
- Project Note or any new object/relation type for OSS projects;
- repository clone, checkout, code/file/blob reads, submodule traversal, or source analysis;
- Git blob/file/tree/subdirectory URL capture;
- arbitrary historical commit, tag, or branch input;
- automatic license detection, license evidence, legal judgment, or OSS publication;
- Book/Web/OSS `source sync` and Web snapshot replacement;
- SQLite projection, FTS, full-text search, or incremental indexing;
- Web UI, FastAPI, Jinja, or Uvicorn;
- Zotero Cloud API, OAuth, writes, or automatic group-library enumeration;
- `bookSection`, batch capture, clipboard, or local-file capture;
- Crossref, OpenAlex, Open Library, or arXiv API fallback;
- direct webpage download or a new Knowlume snapshot store;
- interactive multi-attachment selection;
- automatic Source or Note publication;
- TestPyPI, PyPI, GitHub Release, merge, or version tag.

Existing Snippet files are not out of support: they remain readable and subject to current
validation and publishing checks. Only creation is deferred.

## 7. Checks required before completion

### Function and contract

- All four recognition paths and all explicit overrides have command-level evidence.
- DOI candidate classification covers all accepted Paper types, top-level `book`, zero/multiple or
  mixed exact candidates, unsupported/missing item types, and explicit override failures.
- ISBN checksum/conversion, Web URL canonicalization, configured host extension/exact matching,
  and repository-root parsing follow the frozen rules.
- `add-result-v1` success JSON exactly matches golden fixtures.
- Book page Locator without ISBN/edition, with evidence absent from the Source, or with a mismatched
  normalized ISBN/edition fails.
- Old Web Sources without snapshots remain readable; new captures require complete evidence. Web
  Locator provider, identifier, capture time, and hash exactly match the Source snapshot.
- OSS Source records normalized host/path, default branch, full commit, and `NOASSERTION` only.
- OSS Locator host/path/commit exactly match the Source.
- Repo capture followed by Literature Note creation produces exactly one `summarizes` relation.
- No public or application Snippet creator exists; existing v2 Snippet fixtures still pass.
- Every added Schema field has valid and invalid fixtures; old v2 fixtures remain valid.

### Idempotency, conflict, and atomicity

- Each Source type returns the same ID and `created: false` for the same canonical identity.
- The same repo and unchanged HEAD are idempotent; a changed full HEAD commit creates a different
  Source.
- External aliases that point to different Source IDs never auto-merge.
- Split aliases and cross-Paper/Book DOI collisions return `ADD_IDENTITY_CONFLICT` (3), while
  concurrent file changes return `ADD_WRITE_CONFLICT` (4).
- Source and Note/relation conflicts do not overwrite user changes.
- Adapter, scanner, and transaction failures leave no partial durable files.
- `.knowlume/transactions` and write locks are clean after recovery.

### Security, privacy, and publishing

- Vault contains no absolute path, credential, token, webpage/attachment body, repository body,
  clone, cache, or command log.
- Credential-bearing URLs, unknown/non-root repo shapes, unsafe configured hosts, and automatic
  subdomain inheritance are rejected.
- Git credential prompting, helpers, interactive managers, and system/global URL rewrites are
  disabled; failure messages do not echo secrets, paths, environment values, or remote stderr.
- Zotero is read-only throughout.
- New Sources and Literature Notes are private.
- Project-level OSS uses `license: NOASSERTION`; unresolved rights remain blocked for publication.
- Existing Snippet and publication closure checks continue to fail closed.

### Packaging and compatibility

- Core wheel imports, shows all help, and runs repo/core paths without the Zotero extra.
- Isolated `knowlume[zotero]` loads Paper, Book, and Web adapters.
- Missing Git returns a typed capability diagnostic rather than an import crash.
- Installed repo smoke uses a platform-native fake Git command and never accesses a public network.
- Internal Zotero/Git/scan/invariant diagnostics do not leak through the public `kb add` envelope.
- Wheel Schema/Template bytes match top-level authority.
- Wheel excludes tests, plans, fixtures, Vaults, caches, repository data, and private files.
- Installed CLI works outside the source checkout.
- Install, upgrade, downgrade, and uninstall never mutate a Vault.
- `kb snippet` is absent from source and installed help.

### Required local commands

```powershell
uv run --no-sync pytest -p no:cacheprovider
uv run --no-sync ruff check src tests scripts
uv run --no-sync mypy src tests scripts
uv build
uv run --no-sync python scripts/verify_distribution.py dist
```

Any repository-provided isolated-install and lifecycle scripts must also pass. Then GitHub Actions
must pass:

- Windows, macOS, and Linux;
- Python 3.13 and 3.14;
- complete tests, Ruff, and mypy;
- wheel/sdist build and audit;
- core-only and Zotero-extra isolated installation;
- package lifecycle tests.

Phase 2B is Complete only after the status-only completion commit also passes required CI.

## 8. Git execution rules

- Milestone commits are required implementation checkpoints, but Git operations require explicit
  user authorization.
- Each commit contains only its milestone and excludes failing tests, generated output, and
  unrelated work.
- Do not push a partially registered public command between milestones.
- Push, PR, merge, tag, and package publication are separate permissions.
- Do not mark Phase 2B Complete before remote CI is green.
- Completing Phase 2B does not authorize a package release or version tag.
