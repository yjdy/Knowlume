# Contract v2 templates

These are the active human-readable creation templates for Contract v2. Note sections are role-based and appear only when needed. Every Note includes at least one human section.

The Literature template contains a human section only. `kb note new --type literature` writes its
required `summarizes` relation separately from an explicit `--source SOURCE_ID`; it never creates a
placeholder Fact or guesses a Source.

The Source card template includes Phase 2A Paper identity, Zotero recovery/baseline, and one-primary-
PDF integrity placeholders. Applications omit unavailable optional fields rather than persisting
placeholder values or machine-specific paths.
