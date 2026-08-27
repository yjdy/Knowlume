# Contract v1 to v2 migration

> Status: Active specification  
> Applies to: durable object, body, relation, and locator contracts

Migration is dry-run by default and never guesses semantic intent. The implemented
`kb migrate --from 1 --to 2` command emits a versioned migration report. Apply is prohibited while
blocking findings or required decisions remain and uses the recoverable transaction protocol.

## Mechanical conversions

| V1 shape | V2 result |
|---|---|
| `sec_original_facts` | same section ID with role `fact` |
| `sec_my_interpretation` | same section ID with role `human` |
| `sec_ai_inference` | same section ID with role `ai` |
| `sec_view_evolution` | same section ID with role `evolution` |
| `related_notes` | canonical `related_to` relation shards |
| `supersedes` / `superseded_by` | canonical `supersedes` relation shards |
| one Literature `source_ids` entry | `summarizes` relation |
| global relation collection | one shard per `from_id` |

## Required decisions

- A v1 `evergreen` Note must be classified as Concept or Synthesis. Its maturity remains Evergreen.
- Source IDs on Concept or Synthesis Notes do not imply `cites` or `synthesizes`; migration reports candidates without writing relations.
- V1 fact text has no per-block citation. It is preserved, marked unresolved, and blocked from strict lint and publishing until a human binds Sources and locators.

## Blocking findings

- `ai_assisted: true` without a resolvable reviewed Artifact;
- an AI section containing content without a promoted Artifact;
- missing or duplicate object/section identities;
- references to missing objects or sections;
- public Facts whose Sources or locators cannot be made public-safe.

## Report contract

The executable report shape is [`../../schemas/interfaces/migration-report-v1.schema.json`](../../schemas/interfaces/migration-report-v1.schema.json). Each finding is classified as `change`, `decision`, or `blocker`. Apply requires zero unresolved decisions and blockers.
