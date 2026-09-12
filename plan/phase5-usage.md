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
