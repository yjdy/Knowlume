# Transaction manifest v1

[`transaction-manifest.schema.json`](transaction-manifest.schema.json) defines disposable recovery
state for a Vault multi-file write. Transaction versions are independent from durable object and
configuration versions. Manifests are never durable business facts and never migrate with a Vault.
