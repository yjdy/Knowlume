# Knowlume working rules

These rules apply to the entire repository. They are operational constraints, not a roadmap.

## Authority and versions

Use this order when sources disagree:

1. `schemas/v2/`, interface schemas, and executable contract tests define the current machine contract.
2. This file defines repository working and safety rules.
3. Active documents and accepted ADRs under `plan/` define semantics and architecture.
4. `README.md` is navigation and status.
5. `schemas/v1/`, `templates/v1/`, `tests/fixtures/v1/`, and `plan/archive/` are read-only historical/migration evidence.

Production work creates and modifies Contract v2 only. V1 content is read only through the documented v1→v2 migration flow. Do not duplicate authoritative field tables; link to their owner and update [chapter-map](plan/chapter-map.md) when ownership changes.

## Durable data and vault boundary

- Keep the program repository and personal knowledge vault separate.
- Treat vault Markdown/YAML, relation shards, schemas, templates, migrations, tests, configuration, and source code as durable.
- Treat SQLite projections, caches, derived output, temporary clones, logs, virtual environments, and public staging as disposable.
- Never make disposable state the only source of a business fact.
- Never track machine-specific absolute paths, credentials, tokens, private attachment bodies, large PDF/EPUB files, Zotero storage, temporary repositories, or generated public output without an explicit reviewed policy.
- Application visibility is not encryption or Git-remote protection.

## Contract change workflow

Before editing, read the active design document and accepted ADR that own the behavior. Preserve unrelated user work. For durable-contract changes, use this order:

1. record the decision and migration impact;
2. update the versioned schema;
3. update current templates;
4. add valid and invalid fixtures;
5. update executable acceptance tests;
6. change production parser/domain/application code;
7. provide migration behavior for incompatible existing files.

Do not change a schema, parser, template, or domain model in isolation. Backward-incompatible durable files or machine output require an explicit version decision.

## Knowledge integrity

- Preserve object IDs across rename, move, merge, and supersession; preserve section IDs across heading and type changes.
- Every v2 Note has at least one `role=human` section. Fact, AI, and evolution sections are optional and role-separated.
- Human ideas may have no Source. Facts require one or more valid Source/locator citations. AI blocks require a promoted Artifact.
- Relations target existing objects or stable sections and are written only to `relations/<from_id>.yaml`.
- Never invent line-number or heading-based durable identities, silently delete an object to represent evolution, or overwrite content changed since it was read.
- File writes must be atomic and conflict-aware; multi-file operations require recoverable transaction state.

Detailed semantics belong to [data-model](plan/data-model.md), [sources and adapters](plan/sources-and-adapters.md), and the v2 schemas.

## Distribution discipline

- Treat [`plan/distribution.md`](plan/distribution.md) as the authority for package layout, runtime assets, compatibility, release trust, and rollout gates.
- Keep top-level schemas and templates authoritative. Bundled wheel assets are build copies and must match their source bytes.
- Runtime code accesses bundled assets through `importlib.resources`; it must not search a source checkout or current working directory.
- Keep package and Contract migrations independent. Install, upgrade, downgrade, and uninstall operations must not mutate a vault.
- Keep the core wheel pure Python. Optional Web or adapter imports fail with typed capability diagnostics when their extras are absent.
- Do not publish to TestPyPI, PyPI, or GitHub Releases unless explicitly requested. A release requires the complete test matrix, artifact audit, matching protected tag, and approved release environment.

## Migration discipline

Migration from v1 defaults to dry-run, reports automatic changes, human decisions, blockers, and prohibited guesses, and cannot apply with unresolved required findings. Fixed v1 sections and `sec_original_facts` are migration input only and must not reappear as v2 production requirements.

## AI, privacy, and publishing

- AI output begins as a private, reviewable Artifact. Promotion requires an explicit human action and preserved model/reviewer/time provenance.
- Do not send private objects or attachments to an external model without an explicit caller scope and release policy.
- Public human opinion may be source-free but must remain labeled human. Public facts need complete public citations; public AI needs promoted Artifacts.
- Publishing starts from an explicit allowlist, audits the complete content-dependency closure, and builds isolated staging. Navigation only exposes public targets; private audit edges do not copy private objects into staging.
- Public-safe operations fail closed on private, unresolved, superseded, uncited, unreviewed, unsafe-path, or unresolved-rights dependencies.

Follow [security and publishing](plan/security-publishing.md).

## External systems

- Access Zotero through a supported API, never its private SQLite schema.
- Treat Obsidian as an editor, not the domain database.
- Give Quartz only audited public staging.
- Keep adapter-specific schemas outside the domain layer.
- Use immutable commits for OSS provenance; branch names are insufficient.

## Verification

Run the smallest relevant checks while working and the complete repository suite before handing off a contract or production change:

```powershell
uv run --no-sync pytest -p no:cacheprovider
```

The suite includes internal documentation-link checks. Do not claim a command, compatibility target, phase gate, or feature works unless execution or repository evidence supports it.

For packaging or release changes, also build wheel/sdist, run `scripts/verify_distribution.py`, and install the wheel outside the source checkout before handoff.

Keep [`CLI.md`](CLI.md) synchronized in the same change whenever a CLI command is added, removed, renamed, reassigned to a phase, implemented, or newly verified. Treat it as a delivery ledger, not as a replacement for the interface and roadmap authorities. Mark a command `Verified` only with command-level automated evidence and a passing complete repository suite.

## Git hygiene

- Do not stage, commit, push, rewrite history, or delete branches unless explicitly requested.
- Keep generated, private, and environment-specific files ignored.
- Never bypass a failing contract, security, migration, or publish check.
