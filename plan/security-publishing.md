# Security, privacy, and publishing

> Status: Active — Contract v2
> Authoritative for: trust boundaries, AI promotion, dependency classes, and public publishing

## Default posture

New objects are private unless a human explicitly changes visibility. `private` is an application policy, not encryption or protection from an already configured Git remote. Local paths, credentials, raw private attachments, caches, and temporary output are never publishable inputs. Public-safe operations fail closed.

## Human, fact, and AI content

- Source-free `role=human` content may be searched and published as an opinion, idea, question, or interpretation. Machine output records `provenance_role: human` and empty citations.
- Public `role=fact` blocks require complete citations and public-eligible Sources and locators.
- AI output starts as a private AI Artifact. Ordinary Note content may reference it only after explicit human promotion records the model, reviewer, review time, and audit relation.
- Promotion never converts unsupported prose into fact; fact rules still apply.

## Dependency classes

Relations are classified for publishing:

- **Content dependencies** must be included in and pass the complete public closure.
- **Navigation relations** are rendered only when the target is also public.
- **Private audit relations**, including `promoted_from`, remain in the private vault and are represented in a public manifest only by the minimum required disclosure and integrity hashes.

This classification prevents a private AI Artifact from being copied to staging merely because a promoted block has an audit trail.

## Publish pipeline

```text
explicit public allowlist
        -> content dependency closure
        -> fail-closed audit
        -> isolated atomic staging
        -> preview
        -> publisher adapter
```

Publishing is blocked by private content dependencies, unresolved references, missing stable sections, unreviewed AI, uncited facts, ineligible Sources, unresolved supersession, path escape, unapproved attachments or snippets, and blocking rights findings. A failed build leaves the previous successful staging intact. Only manifest-listed files enter staging, and publishers receive staging plus its manifest rather than the private vault.

Phase 2B project-level OSS Sources record `license: NOASSERTION` because capture does not inspect
repository content or make a license judgment. They remain private by default and fail closed for
public use while rights are unresolved. Existing Snippet publication checks remain in force even
though no Snippet creation command is assigned to a delivery phase.

Phase 2B citation and publication checks also fail closed when a Web Locator does not exactly match
the Source snapshot, a Book page Locator names ISBN/edition evidence absent from or different from
the Source, or an OSS Locator names a different host, project path, or commit. Old v2 Web Sources
without snapshot evidence remain readable but are not public citation dependencies until repaired.

## Context and external models

Callers choose an explicit trusted-local or public-safe scope. Search results and adapters cannot widen it. Private objects or attachments may leave the machine only when an explicit release policy authorizes every selected item and transitive content dependency.

Phase 3 context applies this choice to each item it actually returns. `trusted-local` may include
private local content; `public-safe` excludes unsafe candidates with typed reasons while retaining
eligible results. Phase 3 context emits no AI content. Its per-result check is not a public allowlist,
publish manifest, or staging audit and cannot certify an object or Vault for publication. The frozen
query boundary is recorded in
[`ADR-0016`](decisions/0016-phase3-deterministic-projection-search-context.md).

## Local Web security

Phase 4 is strictly read-only and application-backed as frozen by
[`ADR-0017`](decisions/0017-phase4-local-read-only-application-backed-web.md). The service accepts
only `127.0.0.1`, `localhost`, or `::1`, validates `Host`, and permits a present `Origin` only when it
exactly matches the current loopback origin. Proxy forwarding headers are not trusted, permissive
CORS is forbidden, and no cookie, session, authentication token, or local secret is introduced.
Only GET/HEAD routes exist; there are no mutation, attachment, snapshot, arbitrary-file, JSON API,
OpenAPI, or external-resource routes.

Jinja2 autoescape is global. Markdown disables raw HTML, external images, and `file:`, `data:`,
`javascript:`, or unknown schemes; only renderer-produced safe HTML may bypass template escaping.
Pages expose only Vault-relative paths and permitted normalized metadata. Unexpected errors and
logs omit query text, object bodies, attachment details, adapter stderr, traceback, and absolute
paths.

Every HTML, error, fragment, and static response sets:

```text
Content-Security-Policy: default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Cache-Control: no-store
```

Serving and traversing the interface must leave Vault, relation, configuration, index, state, and
cache bytes unchanged. Writable Web behavior remains a future decision requiring explicit CSRF,
authentication, conflict, audit, and transport design.

## Logging, Git, and deletion

Logs omit private bodies and attachment contents. Visibility changes do not erase Git history or previous publications. Sensitive-data response must explicitly cover history, backups, staging, published sites, and external caches.

Phase 2B repository discovery is anonymous and uses isolated Git configuration. It disables terminal
and GUI prompts, credential helpers, interactive credential managers, and system/global URL rewrites;
credential-bearing URLs are rejected before execution. Public diagnostics omit command details,
task-local paths, environment values, and remote stderr. Tests inject an offline fake Git command
instead of contacting public repositories. The complete policy is frozen by
[`ADR-0015`](decisions/0015-phase2b-provenance-and-anonymous-git.md).

## Legal boundary

Automated checks provide evidence and risk classification, not legal advice. Unclear rights require human confirmation.
