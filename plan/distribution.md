# Distribution and release engineering

> Status: Active
> Authoritative for: Python package layout, bundled runtime assets, compatibility, release trust, and rollout gates

## Product and package identities

- PyPI distribution: `knowlume`; fixed fallback before first publication: `knowlume-kb`.
- Import package: `knowlume`.
- Console command: `kb`.
- Repository and release source: `https://github.com/yjdy/Knowlume`.
- Version source: the static PEP 440 version in `pyproject.toml`; release tag `vX.Y.Z` must match it exactly.

Package version and durable contract versions are independent. Runtime version output reports the
package, object contract, locator, relation, CLI interface, projection, and parser versions together;
Phase 3 adds the independent tokenizer version without changing the package or durable contract
versions.

## Installation profiles

The default distribution contains the CLI and core local functionality. Optional dependency groups are:

| Extra | Capability |
|---|---|
| `web` | FastAPI/Jinja2/Uvicorn local Web interface |
| `zotero` | HTTPX transport for the loopback-only Zotero Local API adapter |
| `all` | every supported optional capability |

Core code must not require an optional dependency merely to import, show help, report versions, inspect bundled assets, or run core tests. A missing extra produces a typed capability diagnostic rather than an import-time crash.

The project resolver uses the official PyPI simple index so `uv.lock` remains portable across local
machines and CI. Machine-specific mirror URLs must not be committed to the lockfile.

## Runtime assets

Top-level `schemas/` and versioned templates remain authoritative source files. Hatch copies them into `knowlume/_assets/` in the wheel. Installed code resolves assets through `importlib.resources`, validates relative asset names, and never searches a source checkout or current working directory.

The wheel allowlist is the `knowlume` Python package, bundled schemas/templates, distribution metadata, and license metadata. It excludes plans, tests, fixtures, vault files, databases, caches, logs, credentials, and machine-specific paths.

## User state and compatibility

`platformdirs` supplies per-user configuration, cache, state, and log directories. These directories contain no durable knowledge. A user-level configuration may point to a default independent vault, but no command implicitly creates or selects a vault when resolution is ambiguous.

Install, upgrade, downgrade, and uninstall operations do not alter vault files. Each application build declares its readable and writable contract range. A newer unsupported vault fails closed; package installation never invokes migration. Contract migration remains explicit, dry-run-first, conflict-aware, and recoverable.

## Update discovery

`kb update-check [--pre] [--json]` is the only package update network operation. It queries public package metadata only when invoked, sends no vault or object information, and never installs an update. Stable releases are selected by default; `--pre` permits prereleases. Network and malformed-response failures use exit code 5.

## Release pipeline and gates

Pull requests test Windows, macOS, and Linux on Python 3.13 and 3.14. Release validation builds one pure-Python wheel and one source distribution, installs the wheel outside the checkout on all three platforms, verifies command/resource behavior, and audits file contents.

Protected `vX.Y.Z` tags enter a manually approved release environment. The pipeline uploads to TestPyPI, runs an installation smoke test, publishes to PyPI using Trusted Publishing/OIDC, creates the matching GitHub Release, and attaches the artifacts, SHA-256 manifest, SBOM, and artifact attestation. No long-lived package-registry token is stored.

- Phase 1 gate: TestPyPI internal package.
- Phase 3 gate: public PyPI prerelease.
- Phase 6B gate: stable `1.0.0` or later.

Publishing remains blocked until the configured PyPI project name is controlled by the release owner.

The `[tool.knowlume.release]` gates in `pyproject.toml` also fail closed. `testpypi-enabled` is opened only with the Phase 1 gate, `pypi-prerelease-enabled` only with Phase 3, and `pypi-stable-enabled` only with Phase 6B. GitHub environment approval is required in addition to, not instead of, these repository gates.

Because the release planner forbids PyPI before TestPyPI, Phase 3 release readiness opens
`testpypi-enabled` and `pypi-prerelease-enabled` together only after the complete feature gate and
normalized project-name control are proven. `pypi-stable-enabled` remains closed. Opening these
repository gates does not authorize a package version change, tag, registry upload, or GitHub
Release; each remains a separate explicit release action.
