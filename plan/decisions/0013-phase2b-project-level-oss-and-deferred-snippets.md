# ADR-0013: Keep Phase 2B OSS capture project-level and defer Snippet creation

- Status: Accepted
- Date: 2026-08-29
- Decision owners: Knowlume maintainers

## Context

Phase 2B must complete the unified Paper, Web, Book, and OSS Source intake promised by
[`ADR-0009`](0009-unified-add-command.md). The earlier draft also proposed repository cloning,
license-file inspection, line-range extraction, publication approval, and a public
`kb snippet add` command.

The product use case for durable code excerpts is not yet established. Implementing it now would
create a large security, legal, path-safety, Git-object, transaction, and user-interface surface
before there is evidence that users need line-level capture. Project-level OSS provenance and an
ordinary reading note already cover the immediate need: record which project and immutable version
was studied, then write a human-maintained overview.

Contract v2 already defines Snippet objects and the `snippet_from` relation. Removing those durable
types would be an incompatible contract change and would make existing or migrated files unreadable.

## Decision

### Project-level OSS Source

Phase 2B keeps `repo` as one of the four `kb add` types. It creates an OSS Source for a complete
repository project, not for a file, directory, code excerpt, or arbitrary historical revision.

The accepted input is an HTTP(S) repository-root URL. GitHub, GitLab, and configured hosts are
recognized automatically; an explicit `--type repo` may select another self-hosted Git server but
must still pass generic project-root and remote-HEAD resolution. Credentials, fragments, query
strings, blob/tree/file/subdirectory routes, and revision selectors are rejected. Nested GitLab
groups remain valid project paths.

The adapter uses read-only Git remote-reference discovery, such as `git ls-remote --symref`, to
resolve the remote default branch and its current full commit. The branch is display metadata; the
full commit is part of canonical identity:

```text
repo:<host>/<project-path>@<full-commit>
```

Phase 2B does not clone the repository, read Git blobs or working-tree files, analyze source code,
or inspect license files. The existing required Source `license` field is written as
`NOASSERTION`. No `license_evidence` field is added in this phase. The Source is private by default,
and ordinary publication rules continue to fail closed on unresolved rights.

Because the commit is discovered from mutable remote HEAD, the adapter must resolve HEAD before it
can perform the final identity lookup. Repeating capture while HEAD is unchanged returns the same
Source ID with `created: false`; a later HEAD commit represents a different immutable Source.

### Overall project notes

Phase 2B does not add a Project Note type or automatically create a Note. A project overview uses
the existing Literature Note workflow:

```text
kb add REPOSITORY_URL --type repo --json
kb note new --type literature --source SOURCE_ID
```

The existing `summarizes` relation records that the Literature Note summarizes the OSS Source. This
reuses the current Note model, stable identity, human sections, and atomic relation behavior.

### Snippet compatibility and indefinite deferral

Contract v2 Snippet objects, templates, fixtures, parsers, migration behavior, relation validation,
and publishing checks remain readable and supported as existing durable data. This ADR does not
delete or weaken them.

No Snippet creation application service or public command is assigned to Phase 2B or to a later
roadmap phase. `kb snippet add` is indefinitely deferred and must not be registered. Reactivating
Snippet creation requires a new accepted ADR based on a validated use case. That ADR must newly
freeze input syntax, immutable content recovery, path and submodule boundaries, line-range
semantics, license evidence, publication approval, idempotency, and multi-file transaction behavior.

### Web and Book refresh boundary

Phase 2B captures a single immutable Web snapshot record. Repeating the same canonical Web URL
returns the existing Source and does not replace its snapshot. Book metadata refresh and Web
snapshot replacement are not added to `source sync` in Phase 2B; the existing Phase 2A Paper/Zotero
synchronization scope remains unchanged.

## Migration impact

There is no v1 or v2 migration. Existing Snippet files and relations retain their current meaning
and validity. Phase 2B makes only additive, backward-compatible Source/config changes needed for
Book edition and configured repository hosts. Exact fields become machine authority only through
the required schema, template, fixture, contract-test, and production-code sequence.

## Consequences

- Phase 2B still delivers one complete four-type `kb add` surface.
- OSS capture proves project identity and immutable version without persisting or even reading
  repository content.
- Overall OSS notes are immediately available through the already verified Literature Note path.
- License auto-detection, code extraction, path traversal defenses for repository content, and
  Snippet publication approval leave the Phase 2B critical path.
- Existing Snippet knowledge remains readable, but the product makes no promise about when a
  creation workflow will return.
- Capturing a moving repository URL at two different HEAD commits intentionally creates two Source
  records; cross-version comparison remains ordinary Note work.

## Alternatives considered

- Implement Snippet creation in Phase 2B: rejected because the use case is unclear and the security,
  legal, Git-content, and transaction surface is disproportionate to current value.
- Delete Snippet from Contract v2: rejected because it is backward-incompatible and unnecessary for
  deferring creation.
- Add a Project Note type: rejected because Literature Note plus `summarizes` already models a human
  reading note centered on an OSS Source.
- Clone repositories to infer license and metadata: rejected because the required project identity
  is available from remote refs and content inspection is outside the selected scope.
- Use a branch name as durable identity: rejected because branch refs are mutable.
- Accept arbitrary commit input in Phase 2B: rejected to keep the public repo path project-level and
  avoid an unresolved revision syntax and recovery surface.
