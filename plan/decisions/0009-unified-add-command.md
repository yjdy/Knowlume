# ADR-0009: Use one deterministic source capture command

- Status: Accepted
- Date: 2026-08-27
- Decision owners: Knowlume maintainers

## Context

Knowlume captures papers, web pages, books, and source repositories through different adapters, but humans and automation need one stable intake surface. Separate public command shapes would duplicate recognition, canonicalization, diagnostics, and idempotency behavior. Automatic recognition is useful only when it remains deterministic and never guesses semantic type.

DOIs require special handling because they may identify papers or books. Repository URLs also require adapter-backed project-root resolution, especially for nested or self-hosted GitLab projects. Phase 2A delivers only the internal paper/Zotero capture slice, while the public command must not imply that all source types work until Phase 2B is complete.

## Decision

The only public capture syntax is:

```text
kb add INPUT [--type paper|web|book|repo] [--json]
```

Automatic recognition is the default. `--type` overrides recognition but never bypasses metadata, canonicalization, schema, snapshot, license, or safety checks. CLI type `repo` maps to durable `source_type: oss`.

Recognition is non-interactive and ordered: explicit type, arXiv, DOI metadata, ISBN checksum, known or configured repository host, then an ordinary HTTP(S) URL. DOI metadata selects paper or book; unavailable or ambiguous metadata requires `--type`. Unknown self-hosted repository URLs are web unless their host is configured; explicit `--type repo` still requires a resolvable project root.

Ambiguous or failed capture writes nothing. Repeated capture of the same canonical identity succeeds idempotently and returns the existing Source ID. The public command and its four type paths are released together in Phase 2B. Phase 2A tests and delivers an internal paper/Zotero capture service without exposing a partial `kb add` command.

Machine-readable success data follows [`add-result-v1`](../../schemas/interfaces/add-result-v1.schema.json) inside the existing CLI envelope v1. No interface-version migration is required because no production CLI has been released.

## Consequences

- Humans, Codex, and scripts use one command and one diagnostic model.
- Type-specific recognizers and capture adapters remain independently testable and deliverable.
- Phase 2A cannot claim a public add command even though its paper backend exists.
- DOI capture depends on metadata for automatic paper/book selection.
- Local files, clipboard bodies, and batch input remain outside the first command contract.

## Alternatives considered

- Positional type syntax such as `kb add paper INPUT`: rejected because automatic input and explicit type occupy competing positions.
- Publish a paper-only parent command in Phase 2A: rejected because the public surface would suggest incomplete automatic capture.
- Treat every DOI as a paper: rejected because the active Source contract also permits book DOI identity.
- Interactive ambiguity prompts: rejected because they make automation nondeterministic.
