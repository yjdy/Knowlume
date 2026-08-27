-- Knowlume rebuildable SQLite projection, contract version 1.
-- Markdown/YAML remains the source of truth. This database may be deleted and rebuilt.

PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO schema_metadata (key, value) VALUES
    ('projection_contract_version', '1');

CREATE TABLE objects (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    subtype TEXT,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    visibility TEXT NOT NULL,
    record_status TEXT NOT NULL,
    workflow_stage TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    checksum TEXT NOT NULL
);

CREATE TABLE relations (
    from_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    to_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    to_section_id TEXT NOT NULL DEFAULT '',
    relation_type TEXT NOT NULL,
    locator TEXT NOT NULL DEFAULT '',
    reason TEXT,
    created_by TEXT,
    PRIMARY KEY (from_id, to_id, to_section_id, relation_type, locator)
);

CREATE TABLE segments (
    segment_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    section_id TEXT NOT NULL DEFAULT '',
    segment_type TEXT NOT NULL,
    heading TEXT,
    text TEXT NOT NULL,
    source_id TEXT REFERENCES objects(id),
    locator TEXT,
    ordinal INTEGER NOT NULL,
    UNIQUE (object_id, section_id, segment_type, ordinal)
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
CREATE INDEX idx_objects_visibility_status
    ON objects(visibility, record_status, workflow_stage);
CREATE INDEX idx_relations_to ON relations(to_id, to_section_id);
CREATE INDEX idx_segments_object_section ON segments(object_id, section_id, ordinal);
CREATE INDEX idx_segments_source ON segments(source_id);
CREATE INDEX idx_object_tags_tag ON object_tags(tag, object_id);

CREATE VIRTUAL TABLE fts_segments USING fts5(
    title,
    text,
    tags,
    object_id UNINDEXED,
    segment_type UNINDEXED,
    visibility UNINDEXED
);
