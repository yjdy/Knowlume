# Interface contracts

Interface contracts have independent versions from durable object and projection contracts.

- `cli-envelope-v1.schema.json`: one JSON document emitted by machine-readable commands.
- `add-result-v1.schema.json`: successful `kb add --json` data, including effective type, canonical identity, Source ID, and created/existing outcome.
- `migration-report-v1.schema.json`: dry-run/apply planning report for contract migration.
- `update-check-result-v1.schema.json`: explicit package update discovery result returned inside the CLI envelope.
