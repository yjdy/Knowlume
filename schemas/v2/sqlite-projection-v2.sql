-- Knowlume rebuildable SQLite projection, contract version 2.
-- Markdown/YAML remains the source of truth. This database may be deleted and rebuilt.

PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;

CREATE TABLE schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO schema_metadata (key, value) VALUES
    ('projection_contract_version', '2');

CREATE TABLE objects (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    subtype TEXT,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    visibility TEXT NOT NULL,
    record_status TEXT NOT NULL,
    workflow_stage TEXT,
    maturity TEXT,
    review_status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    checksum TEXT NOT NULL
);

CREATE TABLE type_transitions (
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    from_type TEXT NOT NULL,
    to_type TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    PRIMARY KEY (object_id, ordinal)
);

CREATE TABLE relations (
    from_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    to_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    to_section_id TEXT NOT NULL DEFAULT '',
    relation_type TEXT NOT NULL,
    locator TEXT NOT NULL DEFAULT '',
    reason TEXT,
    created_at TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id, to_section_id, relation_type, locator)
);

CREATE TABLE sections (
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    section_id TEXT NOT NULL,
    role TEXT NOT NULL,
    heading TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (object_id, section_id),
    UNIQUE (object_id, ordinal)
);

CREATE TABLE segments (
    segment_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    section_id TEXT NOT NULL,
    provenance_role TEXT NOT NULL,
    text TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    ai_artifact_id TEXT REFERENCES objects(id),
    FOREIGN KEY (object_id, section_id) REFERENCES sections(object_id, section_id) ON DELETE CASCADE,
    UNIQUE (object_id, section_id, ordinal)
);

CREATE TABLE citations (
    segment_id TEXT NOT NULL REFERENCES segments(segment_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    source_id TEXT NOT NULL REFERENCES objects(id),
    locator TEXT NOT NULL,
    PRIMARY KEY (segment_id, ordinal),
    UNIQUE (segment_id, source_id, locator)
);

CREATE TABLE tags (
    tag TEXT PRIMARY KEY
);

CREATE TABLE object_tags (
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    tag TEXT NOT NULL REFERENCES tags(tag) ON DELETE CASCADE,
    PRIMARY KEY (object_id, tag)
);

CREATE TABLE parse_errors (
    path TEXT NOT NULL,
    error_code TEXT NOT NULL,
    line INTEGER NOT NULL DEFAULT 0,
    column_number INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL,
    PRIMARY KEY (path, error_code, line, column_number)
);

CREATE TABLE scan_state (
    path TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    modified_at TEXT,
    scanned_at TEXT NOT NULL
);

CREATE TABLE index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX idx_objects_kind_subtype ON objects(kind, subtype);
CREATE INDEX idx_objects_visibility_status ON objects(visibility, record_status, workflow_stage);
CREATE INDEX idx_objects_maturity_review ON objects(maturity, review_status);
CREATE INDEX idx_relations_to ON relations(to_id, to_section_id);
CREATE INDEX idx_sections_role ON sections(role, object_id);
CREATE INDEX idx_segments_object_section ON segments(object_id, section_id, ordinal);
CREATE INDEX idx_segments_role ON segments(provenance_role, object_id);
CREATE INDEX idx_citations_source ON citations(source_id, segment_id);
CREATE INDEX idx_object_tags_tag ON object_tags(tag, object_id);

CREATE VIRTUAL TABLE fts_segments USING fts5(
    title,
    text,
    tags,
    segment_id UNINDEXED,
    object_id UNINDEXED,
    section_id UNINDEXED,
    provenance_role UNINDEXED,
    visibility UNINDEXED,
    record_status UNINDEXED
);
