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

## Context and external models

Callers choose an explicit trusted-local or public-safe scope. Search results and adapters cannot widen it. Private objects or attachments may leave the machine only when an explicit release policy authorizes every selected item and transitive content dependency.

## Local Web security

The service binds to loopback by default. Host and Origin use allowlists; permissive CORS is forbidden. Markdown is sanitized, security response headers are enabled, mutations require CSRF protection and conflict-safe writes, and path operations reject traversal and symlink/junction escape.

## Logging, Git, and deletion

Logs omit private bodies and attachment contents. Visibility changes do not erase Git history or previous publications. Sensitive-data response must explicitly cover history, backups, staging, published sites, and external caches.

## Legal boundary

Automated checks provide evidence and risk classification, not legal advice. Unclear rights require human confirmation.
