# Phase 5 local AI workflow

This guide covers the in-progress implementation under
[ADR-0018](decisions/0018-phase5-local-revision-bound-ai-review.md). Delivery and gate status is in
[phase5-goal](phase5-goal.md) and [CLI.md](../CLI.md).

## Prepare and inspect an Artifact

Use an independent test Vault, initialized with `kb init VAULT`. Prepare a private unreviewed
Artifact in its configured AI directory using the installed `templates/v2/ai-artifact.md` resource
or the authoritative [template](../templates/v2/ai-artifact.md). Fill the stable typed ID, title,
creation date, actual generation tool/model and known input references. Leave review fields null.
Do not invent generation history or edit review_status to simulate an accepted decision.

For an offline tutorial only, the following synthetic Artifact is usable without an external model.
Its model/tool fields explicitly describe a demonstration, not an actual model execution. Save it
under `ai/artifacts/demo.md` in a freshly initialized Vault (respect a custom AI directory):

```yaml
---
schema_version: 2
id: ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E1
kind: ai_artifact
artifact_type: draft
title: Offline demonstration candidate
visibility: private
record_status: active
review_status: unreviewed
created: "2026-09-12"
input_refs: []
generated_by: offline-demonstration
model: synthetic-example-not-a-model-run
prompt_ref: null
reviewed_by: null
reviewed_at: null
---

This synthetic candidate proposes a clearer way to explain a personal knowledge workflow.
```

Do not overwrite an existing ID. Production candidates must retain truthful provenance; if the
original input version is unknown, the later review snapshot cannot reconstruct it.

```text
kb --vault VAULT scan
kb --vault VAULT ai list --json
kb --vault VAULT get ARTIFACT_ID --json
```

The get response contains the full body, input references and `sha256:...` file checksum. Read the
candidate and its referenced material before choosing a decision. `ai list` is metadata-only and
defaults to active unreviewed candidates; use `--review-status all` to inspect prior decisions.

## Review, preview and apply

After inspection, explicitly record accepted or rejected and your local human attribution:

```text
kb --vault VAULT ai review ARTIFACT_ID --decision accepted --reviewer HUMAN_ID --expect-checksum INSPECTED_CHECKSUM --json
```

Rejected content remains a private Artifact. Accepted content is still outside ordinary Notes.
The command changes the checksum; get the Artifact again before promotion. A legacy accepted
Artifact needs this explicit re-review to acquire evidence, while preserving its prior attribution.

Create a target using an existing `kb note new` command and write its human section yourself. Read
the private active Note with `kb get NOTE_ID --json` to obtain its current checksum. Promotion
appends one new AI section; it does not create human conclusions or rewrite existing sections.

```text
kb --vault VAULT ai promote ARTIFACT_ID --into NOTE_ID --section sec_reviewed_ai --actor HUMAN_ID --expect-artifact-checksum ACCEPTED_CHECKSUM --expect-note-checksum NOTE_CHECKSUM --dry-run --json
kb --vault VAULT ai promote ARTIFACT_ID --into NOTE_ID --section sec_reviewed_ai --actor HUMAN_ID --expect-artifact-checksum ACCEPTED_CHECKSUM --expect-note-checksum NOTE_CHECKSUM --apply --json
```

Omitting both mode flags previews only. Inspect preview text and target before apply. Reserved
knowlume structural markers inside candidates are refused, even inside code fences; they cannot be
used to impersonate human/fact sections. This phase accepts private Note targets only.

If a checksum or reviewed input changed, re-read the relevant objects. Changed reviewed candidate
content requires a new unreviewed Artifact, not an automatic retry with a replacement checksum.
If a response was lost after apply, get the Artifact and Note again, check the durable promotion
mapping, and retry the same target/section/actor with current checksums. It returns the existing
result without inserting a duplicate. Changed post-promotion files produce a conflict.
