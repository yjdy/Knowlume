# Portable configuration v1

[`knowlume.schema.json`](knowlume.schema.json) defines the parsed TOML shape of the tracked
`knowlume.toml` Vault marker. Configuration versions are independent from object Contract versions.
Configured paths are portable relative paths; semantic validation additionally rejects overlapping
roots and any resolved path outside the Vault.
