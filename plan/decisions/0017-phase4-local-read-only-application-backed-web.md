# ADR-0017: Keep Phase 4 Web local, read-only, and application-backed

- Status: Accepted
- Date: 2026-09-04
- Decision owners: Knowlume maintainers

## Context

Phase 3 provides scanner-backed object retrieval, a deterministic SQLite projection, filtered FTS,
typed index status, and trusted-local/public-safe query scopes. Phase 4 needs a convenient local
management surface without creating a second parser, search implementation, object model, durable
store, or machine API. A browser interface also creates new network, rendering, privacy, and package
resource boundaries even when it is intended for one user on one machine.

The interface must remain useful when the disposable index is absent or unhealthy, must not turn a
read operation into an index or Vault mutation, and must not expose private content outside the
loopback boundary. Optional Web dependencies must remain isolated from the core package.

## Decision

### Application-backed read model

Phase 4 adds a UI-neutral `CatalogQueryService` in the application layer. Each request obtains one
scanner snapshot and derives Dashboard statistics, Source and Note catalogs, deterministic filters,
fixed pagination, recent-object lists, object details, relations, and scanner findings from that
snapshot. Source and Note lists sort by `updated` descending and stable object ID ascending; repeated
tags use AND semantics and pages contain 50 items.

The Web layer calls this service, the existing permanent-ID object query, Phase 3 `QueryService`, and
`ProjectionStore.status`. It does not invoke CLI callbacks, parse CLI JSON, start subprocesses,
reparse durable files, cache durable bodies, or create a second search/public-safe implementation.
Dashboard, Sources, Notes, and Knowledge Health do not require an index. Search requires a fresh,
compatible index and never creates, rebuilds, or repairs one.

### HTML-only surface

The supported routes are `/`, `/sources`, `/sources/{source_id}`, `/notes`,
`/notes/{note_id}`, `/search`, `/health`, `/assets/app.css`, and
`/assets/htmx.min.js`. They return complete HTML documents or, for a validated HTMX GET, controlled
HTML fragments with identical data and authorization semantics. No HTTP JSON API, OpenAPI,
WebSocket, attachment download, snapshot preview, arbitrary file route, or mutation endpoint is
introduced. JavaScript is optional for every catalog, filter, pagination, and search workflow.

Source and Note detail pages retain stable object and section IDs, roles, citations, locators,
relations, Vault-relative paths, and checksums. Attachment display is metadata-only. Machine
absolute paths, adapter-private errors, attachment bodies, Web snapshot bodies, and AI Artifact
detail pages are excluded.

### Safe rendering and bundled resources

Jinja2 autoescape is enabled globally. Markdown rendering uses `markdown-it-py>=4.2,<5` with raw HTML
disabled and permits only the frozen formatting subset and HTTP(S) links. External images and
`file:`, `data:`, `javascript:`, or unknown schemes are not rendered as active resources. Only the
renderer output crosses the template HTML-safe boundary; titles, tags, findings, query text, and all
other user-controlled values remain autoescaped.

`templates/web/` is the authoritative Web resource directory. The wheel contains a byte-identical
copy under `knowlume/_assets/templates/web/`, loaded only through `importlib.resources`. HTMX 2.0.10,
its upstream license, an integrity record, and the local stylesheet are bundled. Runtime pages load
no CDN, font, image, analytics, telemetry, or other external resource.

### Loopback server boundary

`kb serve [--host 127.0.0.1|localhost|::1] [--port PORT] [--open-browser]` defaults to
`127.0.0.1:8765`. The CLI validates the loopback allowlist and port range before lazily importing
FastAPI, Jinja2, MarkdownIt, or Uvicorn. Help, version, doctor, and core commands work without the
Web extra. Browser opening is opt-in and occurs once only after successful startup.

The application rejects an unapproved `Host`, rejects an `Origin` that is not exactly the current
loopback origin, ignores proxy forwarding claims, enables no permissive CORS, uses no cookies,
sessions, local secrets, or authentication tokens, and registers only GET/HEAD routes. OpenAPI and
interactive documentation are disabled. Uvicorn proxy headers and access logs are disabled.

Every HTML, error, and static response receives the security headers frozen in
[`../security-publishing.md`](../security-publishing.md). Unexpected errors return a generic page and
correlation ID without traceback, private content, query text, attachment details, adapter stderr,
or absolute paths.

### Read-only and diagnostic behavior

Serving and browsing do not write the Vault, relation shards, configuration, state, cache, index, or
logs containing request-sensitive content. Non-GET/HEAD methods return 405. Invalid filters,
queries, or pagination return 400; rejected Host or Origin returns 403; missing or wrong-kind object
IDs return 404; unavailable search indexes return 503 while preserving the Phase 3 `INDEX_*`
diagnostic and displaying the matching explicit CLI recovery command.

The CLI adds `WEB_ARGUMENT_INVALID` (exit 2), `WEB_CAPABILITY_UNAVAILABLE` (exit 5), and
`WEB_SERVER_UNAVAILABLE` (exit 5). Failure to perform an explicitly requested browser open is the
non-fatal `WEB_BROWSER_OPEN_FAILED` warning.

## Migration and release impact

There is no durable Contract, configuration, transaction, projection DDL, tokenizer, segment
algorithm, parser, or package-version change. Contract v2 files require no migration. The `web` and
`all` extras add MarkdownIt; core and `zotero` do not. Distribution verification expands to the Web
resource tree and isolated core/Web installed-wheel smoke coverage. Phase 4 does not authorize a
tag, package upload, GitHub Release, stable release gate, or any Vault mutation during package
lifecycle operations.

## Consequences

- Browser and CLI readers share one interpretation of durable objects, index state, search,
  citations, relations, and public-safe exclusions.
- Private content is available only on an explicitly bounded local interface; loopback remains a
  security boundary that requires adversarial tests rather than an exemption from them.
- Missing or unhealthy SQLite affects Search only and cannot make ordinary catalog browsing mutate
  derived state.
- A future writable, authenticated, LAN, JSON, or richer browser interface requires a separate
  accepted decision and cannot silently extend this slice.

## Alternatives considered

- A separate Web database or parser: rejected because it would create divergent knowledge truth.
- Auto-building or repairing the index on page load: rejected because read requests must remain
  side-effect free and index failures must remain observable.
- Binding to LAN with authentication: deferred because it expands transport, identity, secret, and
  deployment responsibilities beyond Phase 4.
- CDN-hosted HTMX or a frontend build chain: rejected because runtime network access and dependency
  drift weaken offline installation, privacy, and artifact reproducibility.
- An HTTP JSON API or OpenAPI surface: rejected because existing CLI JSON owns programmatic access
  and a new machine contract would require separate versioning.
