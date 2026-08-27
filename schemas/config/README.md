# Configuration contracts

Configuration versions are independent from object, locator, relation, interface, projection,
parser, and transaction versions.

- [`v1/knowlume.schema.json`](v1/knowlume.schema.json) validates the parsed TOML mapping stored in a
  vault-root `knowlume.toml`.

The file is portable durable configuration. It contains a stable vault identity, the writable object
Contract version, and relative POSIX paths for durable object collections. Schema-valid paths must
also be pairwise distinct and non-overlapping after normalization. Machine-local paths, credentials,
adapter endpoints, locks, and transaction records are not valid vault configuration fields.

