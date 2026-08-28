# Data model

> Status: Active  
> Baseline: Contract v2
> Authoritative for: object semantics, identity, Note bodies, lifecycle, provenance, and relations

Executable contracts are under [`../schemas/v2/`](../schemas/v2/README.md). Contract v1 is historical and readable only for migration.

## Objects and identity

| Kind | Responsibility |
|---|---|
| Source | durable metadata and route to original material |
| Note | human-maintained knowledge with at least one human section |
| Snippet | reviewed OSS extract fixed to an immutable commit |
| AI Artifact | private AI output before or after explicit review |

Every object has a permanent typed ID. File, title, heading, and Note type changes preserve IDs. Duplicate IDs block strict lint, migration apply, and publishing. Claim is not a v2 object.

### Paper Source identity and capture eligibility

A Source ID remains the durable identity when an external identifier, adapter route, attachment, or
filename changes. For Paper Sources, DOI and arXiv are canonical external identifiers used for
recognition and duplicate detection. Zotero library, item, and attachment keys are recovery routes;
they are not domain identity.

An existing Contract v2 Source can remain schema-valid with only a Zotero route. Phase 2A automated
capture is deliberately stricter: resolved metadata must contain DOI or arXiv identity before a new
Source can be written. This distinction preserves existing files without allowing nondeterministic
new capture.

When DOI and arXiv are both known, DOI is the preferred external identity and arXiv is an alias.
Matching either value resolves the existing Source. If the identifiers resolve to different Source
IDs, the operation stops for human review and never merges them automatically. arXiv version is
material-recovery metadata rather than part of duplicate identity.

### Source workflow

Source workflow moves explicitly and one step at a time:

```text
inbox -> reading -> processed -> integrated
```

Requesting the current stage is idempotent. Skipping a stage, moving backward, or advancing beyond
`integrated` is invalid. Adapter synchronization does not own or change workflow stage.

## Note types and maturity

| Type | Meaning | Semantic requirement |
|---|---|---|
| `idea` | source-free idea, question, hypothesis, or experience | maturity is seed/developing only |
| `literature` | reading note centered on original material | at least one `summarizes` Source |
| `concept` | structured understanding of a concept | may be source-free |
| `synthesis` | conclusions across Sources or Notes | mature/public requires at least two `synthesizes` targets |

Maturity is `seed`, `developing`, `mature`, or `evergreen`. Evergreen is not a Note type. Idea may evolve in place to Concept; the Note ID and section IDs remain stable, and frontmatter `type_history` records the transition actor and time.

## Role-based Note bodies

Contract v2 sections use:

```markdown
<!-- knowlume:section id=sec_core_idea role=human -->
## Core idea
```

Roles are `human`, `fact`, `ai`, and `evolution`. Every Note contains at least one human section; other roles are optional. Section IDs are unique within a Note and survive heading, path, and Note-type changes.

A Fact block carries adjacent citation metadata with one or more Source IDs and source-specific locators. Every non-heading block in a fact section must have metadata. Uncited prose belongs in a human section and is never silently reclassified.

An AI block carries an adjacent Artifact ID. The Artifact must be promoted and retain model, input references, reviewer, and review time. Accepted-but-unpromoted or unreviewed AI remains outside ordinary Notes.

Source-free human content may be searched and published as opinion or interpretation. It never appears in the Facts surface, and machine output reports human provenance with an empty citation list.

## Relations

Relations are stored at `relations/<from_id>.yaml`; inverse navigation is derived. Note frontmatter does not duplicate source, related-note, or supersession links.

| Relation | Valid direction |
|---|---|
| `cites` | Note -> Source |
| `summarizes` | Literature Note -> Source |
| `synthesizes` | Synthesis Note -> Source/Note |
| `supports` / `contradicts` | Source/Note -> Note or stable Note section |
| `related_to` | Note <-> Note, stored once in canonical ID order |
| `snippet_from` | Snippet -> OSS Source |
| `derived_from` | Note/AI Artifact -> Source/Note |
| `promoted_from` | Note -> AI Artifact |
| `supersedes` | new object -> old object of the same kind |

Canonical relation identity excludes reason, time, and actor. AI may propose a relation only as a private `relation_candidate` Artifact; trusted relation writes require human review or a deterministic system action.

## Evolution and contract versions

Merge and supersession preserve old objects instead of deleting them. Search and publishing surface or audit superseded dependencies. Contract v1 fixed sections and duplicated frontmatter links are migration inputs only; the active mapping and blockers are defined in [`migrations/v1-to-v2.md`](migrations/v1-to-v2.md).

Phase 2A extends Paper metadata compatibly within Contract v2 and keeps existing v2 Sources
readable. The accepted semantics and migration boundary are recorded in
[`ADR-0012`](decisions/0012-phase2a-paper-zotero-design.md); exact machine fields remain owned by
the versioned schemas.
