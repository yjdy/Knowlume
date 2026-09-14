# ADR-0018: Keep Phase 5 AI review local, revision-bound, and transactional

- Status: Accepted
- Date: 2026-09-11
- Implementation authority: the user requested development according to the Phase 5 execution goal.

## Decision and scope

Implement the local Artifact list, explicit human review, dry-run/apply promotion, machine workflow,
and explicit doctor probes described in [phase5-goal](../phase5-goal.md). Artifact generation,
external model transport, Web writes, publication and automatic execution of relation candidates
remain outside this decision. An actor argument records a caller's human attribution, not identity
authentication. The source remains a private Artifact after promotion.

## Revision-bound review

The optional `review_evidence` and `promotion` properties extend Contract v2 AI Artifacts. Their
exact shapes belong to [objects schema](../../schemas/v2/objects.schema.json), not duplicate tables.
Each evidence value has its own version, initially 1. New review writes evidence; new promotion
requires it. Existing unextended objects remain readable. Unreviewed objects can be reviewed;
legacy accepted objects can explicitly be reviewed again while retaining their previous reviewer
and time. Legacy rejected/promoted objects are never silently upgraded or given invented history.

Evidence hash algorithm v1 is SHA-256 of UTF-8 JSON with sorted keys, compact separators, no ASCII
escaping and no NaN values. The payload contains the normalized Artifact frontmatter excluding
review_status, reviewed_by, reviewed_at, review_evidence and promotion, plus its parsed body.
LF and CRLF in text normalize to LF; the parser's existing outer-body whitespace normalization is
retained. This semantic digest is separate from the expected raw-file SHA-256 used for concurrency.
Formatting-only input-file changes still invalidate input checksums conservatively.

Input revisions record safe Vault-relative paths and raw SHA-256 values, including absence of
relevant relation shards. Traverse input references, Note Fact citations, Snippet source_id and content relations
recursively, deduplicate shared dependencies, reject cycles, missing sections and non-active or
superseded dependencies. Exclude navigation and private audit edges from recursive expansion.
An empty input_refs list is permitted and never confers Fact provenance. The snapshot certifies
the locally reviewed versions, not undocumented model-generation-time versions. prompt_ref is a
safe portable relative reference only: never dereference it or send it outside the machine.

Review follow-up (2026-09-12): a Snippet's required Source field is a content dependency even when
the optional snippet_from relation is absent. Capture that Source's revision and relation-shard
absence/presence, and apply the same active/non-superseded checks as other dependencies. This fixes
an incomplete dependency walk; it does not create Snippets or require a new relation on old files.
The evidence shape, hash algorithm, parser and Contract versions stay unchanged. Existing files
remain readable; accepted evidence produced by the incomplete walk cannot authorize promotion or
be silently backfilled. Prepare a new unreviewed candidate in that case. Completed promotions still
use their recorded post-state for no-op retries; no migration or retroactive rewrite occurs.

Unreviewed may become accepted or rejected. Same-decision, same-reviewer retries with current
checksums and valid evidence are byte-preserving. Other reversals, altered content, changed inputs
or changed reviewers fail closed. Revising a reviewed candidate requires a new unreviewed Artifact.
Legacy accepted re-review is the sole evidence-upgrade exception and retains prior attribution.

## Promotion and recovery

Promotion requires an accepted, active Artifact, valid review evidence, explicit human actor,
current Artifact and Note file checksums, an existing private active Note and a fresh section ID.
Default is dry-run; apply is explicit. Append the entire parsed Artifact body as one AI block in a
new AI section, with adjacent Artifact metadata. Reject reserved knowlume metadata markers anywhere
in the candidate (including code fences), empty content or any failed parser round-trip. Ordinary
Markdown headings, lists and fenced code remain literal AI content. Existing Note body bytes and
sections must be preserved; only necessary frontmatter metadata and the new section are written.

Persist promotion time/actor, Note/section identity and resulting Note/shard checksums in Artifact
promotion evidence. A single recoverable transaction updates Artifact, Note and its promoted_from
shard. Preserve review attribution separately. Completed retries validate this recorded post-state
and exact target/actor, not the pre-promotion input Note revision. Subsequent edits cause conflict,
never repair or duplicate insertion. Different targets require a different Artifact.

Extend the transaction interface with read preconditions checked under the Vault lock before
preparation, before each replacement and before recording committed state. Recheck every destination
immediately before replacement. During commit compare already-written destinations against their
replacement checksums. Roll back on observed dependency changes. Recovery needs only write entries,
so read preconditions do not change the durable manifest shape. Transaction v1 adds ai-review and
ai-promote operation labels; existing recovery is operation-independent. Existing writers remain
unchanged. Cooperative writers use the lock; external editors are guarded by checksum observations,
not claimed to participate in an operating-system multi-file atomic transaction.

Review and promotion retain all business facts in durable files. Index refresh remains best-effort
after success. A missing or stale index cannot prevent these workflows or trigger implicit repair.

## Command and machine contract

Freeze the candidate parameters and defaults in [interfaces](../interfaces.md). AI commands use
CLI envelope v1 and separate list/review/promote result schemas v1. Expected checksums use the
existing `sha256:`-prefixed lowercase SHA-256 format. No mutation occurs merely by printing JSON. Usage failures
also emit a single failure envelope when --json was requested, with no private input in diagnostics.

New codes: AI_ARGUMENT_INVALID (2), AI_ARTIFACT_NOT_FOUND (3), AI_STATE_INVALID (3),
AI_REVIEW_EVIDENCE_INVALID (3), AI_REVIEW_EVIDENCE_UNSUPPORTED (3), AI_TARGET_INVALID (3),
AI_INPUT_INVALID (3), AI_CONTENT_UNSAFE (6), AI_INPUT_CHANGED (4), AI_PROMOTION_CONFLICT (4).
Reuse VAULT_* and INDEX_REFRESH_FAILED for existing failure categories.

No-probe doctor preserves report v1, including its historical local user_paths and exit behavior.
Explicit repeatable probes produce report v2 with fixed order package checks, vault, sqlite, git,
zotero. Unselected probes are skipped; selected probes are passed, unavailable or failed. Only
explicit Zotero selection contacts the existing loopback API, never attachment endpoints. Git
invokes only local version discovery with timeout. SQLite capability testing is in-memory; Vault
index inspection is read-only. Reports aggregate all selected outcomes; healthy means installation
checks and all selected probes passed. V2 unhealthy reports use failure envelopes while retaining
report data; exit priority is security (6), conflict (4), invalid data (3), unavailable (5). Bad probe
names are usage errors (2). Unknown exceptions yield sanitized typed failures.

Diagnostic composition follow-up (2026-09-12): concrete Git, Zotero, filesystem and SQLite probes
live in a local adapter behind one probe port. The application module only selects probes,
aggregates results and assigns exit policy; the CLI supplies the adapter and installation report.
The existing application scanner's health check is passed into the adapter at composition time,
so the diagnostic adapter does not import application services or duplicate scanning semantics.
Vault discovery occurs inside the selected probe's protected call, so read/decoding failures are
reported without suppressing unrelated selected probes. This changes no CLI or report version.

## Compatibility, versions and migration

Object Contract stays v2; parser advances from 1 to 2 when the production parser learns evidence.
Projection DDL, tokenizer, relation, configuration and envelope versions do not change. A parser-1
index is incompatible and requires explicit rebuild, not silent migration. New software reads old
v2 files, but older strict parsers/schemas can reject evidence-extended objects. Package downgrade
does not remove these fields and does not promise forward readability. Unknown evidence versions
or malformed evidence block affected writes and preserve the original files.

Schema/template/fixture/contract tests precede production parser changes. Installation, upgrade,
downgrade, uninstall and read operations never migrate a Vault. No historical v1 objects are edited.
Doctor report v2 is opt-in, so existing v1 consumers retain their interface. Package version and
release gates do not change. Supported-platform feature and completion CI remain required.

## Alternatives

Using only review_status loses the version that was reviewed. Storing evidence only in SQLite or a
transaction directory loses audit facts after rebuild/cleanup. Automatically re-reviewing modified
content substitutes a machine decision for human intent. Extending Web mutations would require a
separate transport/authentication/CSRF design. All are rejected for this phase.
