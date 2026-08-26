# Security, privacy, and publishing

> Status: Active  
> Baseline: v0.1  
> Authoritative for: trust boundaries, AI isolation, visibility enforcement, and public publishing

## Default posture

- Every new object is private unless a human explicitly changes its visibility.
- Unreviewed AI remains private and outside facts, default search/context, and publishing.
- Local paths, raw attachments, credentials, private images, caches, and temporary files are never publishable inputs.
- Security checks fail closed for public output.

Object field semantics belong to [`data-model.md`](data-model.md); this document defines enforcement.

## Context scopes

Context consumers select an explicit scope:

| Scope | Permitted material |
|---|---|
| trusted local/private | private and public reviewed human knowledge; AI only when explicitly requested |
| public-safe | public allowlist closure only; no private dependency or unpromoted AI |

`kb context` does not guess scope from terminal, caller name, or output path. A public-safe request cannot be widened by a search result or adapter.

## AI isolation

AI writes begin as `ai_artifact`. Promotion is an explicit human-reviewed use case that records artifact ID, reviewer, review time, source IDs, model identifier, and resulting Note ID.

AI assistance does not convert unsupported prose into fact. A promoted fact still needs a valid Source ID and locator. Rejected artifacts remain traceable but excluded from ordinary retrieval.

Future external LLM integrations require an allow policy specifying which objects and sections may leave the machine. Sending data is denied unless the active scope authorizes every transitive dependency.

## Publish pipeline

```text
explicit public allowlist
        -> dependency closure
        -> audit
        -> atomic public-staging build
        -> preview
        -> publisher adapter
```

Knowlume never gives the complete private vault to Quartz and relies on downstream filtering.

## Audit rules

Publishing is blocked by:

- direct or transitive public-to-private object, section, image, or attachment dependencies;
- broken/unresolved links or missing stable sections;
- unpromoted AI artifacts or unreviewed AI content;
- superseded dependencies without an accepted resolution;
- absolute local paths, path traversal, symlink/junction escape, or temporary files;
- raw PDF/EPUB material outside an explicit reviewed attachment policy;
- OSS snippets without immutable commit, path/range, license, and publication approval;
- unresolved copyright, license, attribution, or redistribution findings marked blocking.

The audit produces a versioned manifest containing included object IDs, dependency edges, source hashes, exclusions, warnings, blocking findings, and tool/contract versions.

## Staging guarantees

- Staging is rebuilt into a temporary directory and atomically promoted after audit success.
- Previous successful staging remains intact when a build fails.
- Only manifest-listed files may appear in staging.
- Generated output is not copied back into durable knowledge.
- Publisher adapters receive staging plus its manifest, never repository-wide access.

## Local Web security

The Web service binds to loopback by default. Mutations require CSRF protection and conflict-safe writes. Markdown rendering is sanitized. File-open and adapter calls use structured arguments and validated roots rather than shell-composed paths.

Any future non-loopback mode requires authentication, authorization, secure transport, and a separate threat review.

## Logging and errors

Logs omit full private bodies and attachment contents by default. Diagnostics may include object IDs, safe relative paths, hashes, error categories, and redacted external identifiers. Error reports must not convert private content into telemetry.

## Git and deletion

Changing an object from public to private does not erase earlier Git history or already published copies. Sensitive-data incidents require an explicit response covering Git history, backups, staging, published sites, and external caches.

## Legal boundary

Automated checks provide evidence and risk classification, not legal advice. Human confirmation remains mandatory when rights are unclear.
