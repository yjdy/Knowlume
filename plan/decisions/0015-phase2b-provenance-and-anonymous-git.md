# ADR-0015: Freeze Phase 2B provenance coherence and anonymous Git resolution

- Status: Accepted
- Date: 2026-08-29
- Decision owners: Knowlume maintainers

> Phase 2B scope, project-level OSS capture, and deferred Snippet creation are frozen by
> [`ADR-0013`](0013-phase2b-project-level-oss-and-deferred-snippets.md). Phase 2A acceptance and
> Phase 2B Zotero Paper/Book classification are frozen by
> [`ADR-0014`](0014-phase2a-acceptance-and-phase2b-zotero-classification.md).

## Context

Phase 2B already has a stable four-Source scope, but three implementation boundaries require an
explicit decision before Contract work begins:

- a new Web capture needs stronger snapshot evidence than the backward-compatible v2 Source schema
  requires from every existing file;
- Book and OSS locators must agree with the Source version they cite instead of carrying independent
  provenance values;
- repository-host configuration and Git reference discovery need deterministic trust, authentication,
  and offline-test rules.

Making `snapshot_ref` globally required would invalidate readable v2 Web Sources. Allowing a Locator
to introduce provenance absent from, or different from, its Source would make a Fact or relation cite
material that the Source does not identify. Allowing ambient Git credentials or URL rewrites would
make supposedly anonymous capture depend on machine-specific secrets and could redirect the command
away from the normalized repository URL.

## Decision

### Web capture and backward compatibility

An existing v2 Web Source remains readable, scannable, listable, and showable when it has only a
canonical URL and `captured_at`. Contract v2 is not revised to require `snapshot_ref` globally, and
there is no automatic migration or rewrite.

New unified Web capture is stricter. It requires exactly one exact top-level Zotero `webpage` item
and exactly one child attachment with all of the following properties:

- `itemType` is `attachment`;
- `parentItem` equals the selected webpage item key;
- `linkMode` is `imported_url`;
- `contentType` is `text/html` or `application/xhtml+xml`;
- `dateAdded` is present and parseable;
- the attachment is recoverable and contains non-empty bytes.

The Source and its `snapshot_ref` use the attachment `dateAdded` as the same `captured_at` value. The
snapshot SHA-256 is computed from the recovered bytes. Attachment bodies and storage paths remain
transient. Zero or multiple exact webpage candidates, zero or multiple eligible snapshots, or any
invalid or unavailable required snapshot evidence returns `ADD_METADATA_UNAVAILABLE` and writes
nothing.

A Web Locator must exactly match its Source snapshot provider, identifier, capture time, and SHA-256.
An old Web Source without complete and coherent snapshot evidence remains readable but cannot support
a new Web citation or pass public dependency closure until it is recaptured or explicitly repaired
by a future reviewed workflow. Phase 2B adds neither such a repair command nor Web synchronization.

### Book and OSS locator coherence

ISBN-10 is checksum-validated and normalized to ISBN-13 before comparison. Book `edition` is compared
as the complete case-sensitive string after trimming its outer whitespace.

A Book page Locator contains at least one of ISBN or edition. Every ISBN or edition present in the
Locator must also exist on the Source and match its normalized value. A Locator cannot introduce
version information absent from the Source. When the Source has both values, the Locator may carry
one; if it carries both, both must match. A DOI-only Book Source can be captured, but it cannot
support a page Locator until the Source has ISBN or edition evidence.

An OSS Locator must match the Source's normalized host, complete project path, and full immutable
commit. Branch names are display metadata and cannot satisfy or alter locator identity.

Fact and relation validation reuse the existing `FACT_LOCATOR_MISMATCH` and
`RELATION_LOCATOR_MISMATCH` findings. Finding details identify the mismatched fields; no parallel
finding vocabulary is added. Existing inconsistent objects remain parseable, but citations and
public dependency closure fail closed.

### Repository host configuration

Configuration v1 keeps `config_version = 1` and gains optional
`[capture].repository_hosts`. The configured set extends, rather than replaces, the built-in
`github.com` and `gitlab.com` set. A missing section or an empty list therefore has the same default
effective hosts.

Each configured value is a bare DNS hostname. Normalization lowercases it, converts it to an IDNA
A-label, and removes one terminal root-domain dot. Scheme, credentials, port, path, wildcard, IP
literal, `localhost`, whitespace, an empty value, and duplicates after normalization are invalid.
Matching uses the complete normalized hostname; configuring a parent does not authorize a subdomain.

GitHub project roots contain exactly owner and repository path segments. GitLab and configured hosts
accept nested project paths with at least two segments. Provider file/tree routes, including `/-/`,
are not roots. One terminal `.git` and one trailing slash may be removed during normalization.
Unknown hosts default to Web during automatic recognition. Explicit `--type repo` may select another
credential-free HTTP(S) host, but still requires generic root validation and successful remote HEAD
resolution.

### Anonymous and isolated Git discovery

Phase 2B accepts only repository URLs that require no authentication. It invokes a narrow command
equivalent to `git ls-remote --symref URL HEAD`; it does not clone, fetch, checkout, read objects, or
inspect repository content.

The adapter disables terminal and GUI credential prompts, credential helpers, interactive Git
Credential Manager, and system/global URL rewrites. It uses disposable isolated Git configuration
and a platform-appropriate rejecting askpass helper. No credential, task-local path, environment
value, remote stderr, or command detail is persisted or exposed through the public diagnostic.

Missing Git, authentication requirements, access failure, timeout, malformed output, symbolic-ref
loops, and unborn HEAD become typed adapter failures and are translated by `kb add` to
`ADD_METADATA_UNAVAILABLE`.

Git unit tests use an injectable command port. Installed-wheel smoke tests place a platform-native
fake `git` executable on a temporary `PATH`: an executable shim on POSIX and `git.cmd` on Windows.
The fake emits deterministic symbolic-HEAD and full-commit responses and exercises unavailable,
nonzero, malformed, and authentication-required failures. No Phase 2B Git test contacts a public
network.

## Migration impact

There is no object-contract, configuration, locator, relation, or machine-interface version bump.
Old v2 Web Sources remain readable. New Source fields and configuration syntax still follow the
ADR -> Schema -> template -> fixture -> contract test -> production code order. The new coherence
rules are semantic validation and publishing rules, not an automatic durable-data migration.

## Consequences

- New Web Sources always have immutable, recoverable capture evidence while old readable v2 data is
  preserved.
- A citation cannot silently name a different Book edition, Web snapshot, or OSS commit than its
  Source.
- Repository auto-recognition is deterministic across configuration, IDNA, case, and subdomains.
- Repo capture neither prompts for nor consumes ambient credentials and is testable without public
  network access.
- Project-level OSS scope, `license: NOASSERTION`, Literature Note reuse, and indefinite Snippet
  deferral remain unchanged.

## Alternatives considered

- Require `snapshot_ref` from every v2 Web Source: rejected because it would invalidate existing
  readable files without a versioned migration.
- Allow Locator provenance to supplement a Source: rejected because the Source would no longer be
  the durable authority for the cited material.
- Let configured hosts replace the built-in set or authorize subdomains: rejected because an empty
  or broad configuration would unexpectedly change recognition behavior.
- Use ambient Git credential helpers and user configuration: rejected because behavior would depend
  on machine-local secrets and URL rewrites.
- Use live public repositories in tests: rejected because CI and installed-wheel verification must
  be deterministic and offline.
