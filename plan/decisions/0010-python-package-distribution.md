# ADR-0010: Distribute Knowlume as a cross-platform Python package

- Status: Accepted
- Date: 2026-08-27
- Decision owners: Knowlume maintainers

## Context

Knowlume must run on computers that do not contain its source checkout. The application and personal vault are already separate, but the repository has no production package, runtime asset resolver, release pipeline, or upgrade contract. Shipping a desktop runtime would add a second installation architecture before the CLI and local Web boundaries are stable.

## Decision

Publish a Python distribution named `knowlume` to PyPI and attach the same wheel and source distribution to GitHub Releases. If the normalized PyPI name cannot be controlled before the first upload, the distribution name changes once to `knowlume-kb`; the executable remains `kb`.

The import package is `knowlume`, stored under `src/knowlume`. Python support remains `>=3.13,<3.15` on Windows, macOS, and Linux. Users install through `pipx` or `uv tool`.

Core installation remains pure Python. Web and adapter dependencies use optional extras. Authoritative schemas and templates remain at the repository root and are copied into the wheel under `knowlume/_assets` by the build configuration. Runtime code accesses them only through `importlib.resources`.

Package upgrades never move, delete, or implicitly migrate a vault. Contract migration remains an explicit application operation. Update discovery is explicit through `kb update-check`; Knowlume performs no background update request and never self-installs an update.

Releases use protected Git tags, a three-platform test matrix, PyPI Trusted Publishing, GitHub artifact attestations, checksums, and an SBOM. The TestPyPI gate follows Phase 1, public PyPI prereleases follow Phase 3, and stable `1.0.0` follows Phase 6B.

## Consequences

- A Python 3.13 runtime plus `pipx` or `uv` is a user prerequisite.
- Source checkouts and installed wheels use the same package-resource API.
- Release tests must install the built artifact outside the repository and audit its contents.
- Package, object contract, locator, relation, projection, interface, and parser versions remain independent.
- A future desktop installer requires a separate ADR and does not change vault ownership.

## Alternatives considered

- Bundle Python in native installers: deferred until the CLI and Web application are stable.
- Publish only source archives: rejected because `pipx` and `uv tool` require ordinary Python package metadata.
- Read schemas from the source repository at runtime: rejected because an installed wheel has no repository layout.
- Automatically migrate vaults during package upgrade: rejected because rollback and durable-data safety would become package-manager side effects.
