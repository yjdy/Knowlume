# Interface contracts

Interface contracts have independent versions from durable object and projection contracts.

- `cli-envelope-v1.schema.json`: one JSON document emitted by machine-readable commands.
- `add-result-v1.schema.json`: successful `kb add --json` data, including effective type, canonical identity, Source ID, and created/existing outcome.
- `migration-report-v1.schema.json`: dry-run/apply planning report for contract migration.
- `update-check-result-v1.schema.json`: explicit package update discovery result returned inside the CLI envelope.
- `finding-v1.schema.json`: stable scanner/lint diagnostic shape; paths are Vault-relative.
- `source-list-result-v1.schema.json`: scanner-backed Source query and inbox results.
- `source-show-result-v1.schema.json`: normalized Source lookup results.
- `source-sync-result-v1.schema.json`: Zotero synchronization outcomes.
- `source-workflow-result-v1.schema.json`: explicit Source workflow transition outcomes.
- `grep-result-v1.schema.json`: index-independent durable-file navigation hits.
- `get-result-v1.schema.json`: normalized generic object lookup with citations and relations.
- `index-result-v1.schema.json`: build, rebuild, and read-only status results.
- `search-result-v1.schema.json`: ranked, traceable FTS results and explicit filters.
- `context-result-v1.schema.json`: scoped, grouped context with exclusions and character bounds.
