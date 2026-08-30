from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from knowlume.adapters.contract_v2 import locator_data, parse_locator
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.constants import (
    LOCATOR_VERSION,
    OBJECT_CONTRACT_VERSION,
    PARSER_VERSION,
    PROJECTION_VERSION,
    RELATION_SCHEMA_VERSION,
    SEGMENT_ALGORITHM_VERSION,
    TOKENIZER_VERSION,
)
from knowlume.domain.models import (
    AIArtifact,
    AIBlock,
    FactBlock,
    Note,
    NoteBody,
    Snippet,
    Source,
)
from knowlume.domain.search import (
    ContextScope,
    SearchFilters,
    SearchHit,
    literal_fts_query,
    segment_id,
    tokenize,
)
from knowlume.domain.validation import locator_mismatched_fields
from knowlume.domain.values import DomainError, RecordStatus, Visibility
from knowlume.ports.vault import Vault
from knowlume.resources import read_asset_text

BODY_SECTION = "__body__"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_entries(scan: ScanResult) -> tuple[tuple[str, str], ...]:
    entries = [(item.path, item.checksum) for item in scan.objects.values()]
    entries.extend((item.path, item.checksum) for item in scan.relation_shards.values())
    return tuple(sorted(entries))


def snapshot_hash(scan: ScanResult) -> str:
    digest = hashlib.sha256()
    for path, checksum in _snapshot_entries(scan):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(checksum.encode("ascii"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _runtime_versions() -> dict[str, int]:
    return {
        "projection": PROJECTION_VERSION,
        "object_contract": OBJECT_CONTRACT_VERSION,
        "locator": LOCATOR_VERSION,
        "relation_schema": RELATION_SCHEMA_VERSION,
        "parser": PARSER_VERSION,
        "tokenizer": TOKENIZER_VERSION,
        "segment_algorithm": SEGMENT_ALGORITHM_VERSION,
    }


def _metadata_versions(metadata: dict[str, str]) -> dict[str, int] | None:
    try:
        return {name: int(metadata[f"{name}_version"]) for name in _runtime_versions()}
    except (KeyError, ValueError):
        return None


def _changed_paths(scan: ScanResult, indexed: dict[str, str]) -> list[str]:
    current = dict(_snapshot_entries(scan))
    return sorted(
        path for path in current.keys() | indexed.keys() if current.get(path) != indexed.get(path)
    )


class SQLiteProjection:
    """Disposable, scanner-derived projection and deterministic FTS backend."""

    def __init__(self, *, ddl_reader: Any = read_asset_text) -> None:
        self._ddl_reader = ddl_reader

    @staticmethod
    def database_path(vault: Vault) -> Path:
        return vault.path("state") / "kb.sqlite"

    @staticmethod
    def _lock_path(vault: Vault) -> Path:
        return vault.path("state") / "locks" / "index.lock"

    @contextmanager
    def _writer_lock(self, vault: Vault) -> Iterator[None]:
        lock = self._lock_path(vault)
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise DomainError("INDEX_BUSY", "another index writer is active") from error
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            yield
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
            lock.unlink(missing_ok=True)

    @staticmethod
    def _read_metadata(connection: sqlite3.Connection) -> dict[str, str]:
        return dict(connection.execute("SELECT key, value FROM index_metadata").fetchall())

    @staticmethod
    def _read_scan_state(connection: sqlite3.Connection) -> dict[str, str]:
        return dict(connection.execute("SELECT path, checksum FROM scan_state").fetchall())

    @staticmethod
    def _counts(connection: sqlite3.Connection) -> dict[str, int]:
        return {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in ("objects", "relations", "sections", "segments", "citations")
        }

    def status(self, vault: Vault) -> dict[str, object]:
        database = self.database_path(vault)
        scan = scan_vault(vault)
        current_snapshot = snapshot_hash(scan)
        base: dict[str, object] = {
            "operation": "status",
            "state": "missing",
            "versions": {"runtime": _runtime_versions(), "index": None},
            "snapshot": {"current": current_snapshot, "indexed": None},
            "counts": {
                name: 0 for name in ("objects", "relations", "sections", "segments", "citations")
            },
            "changed_paths": sorted(path for path, _ in _snapshot_entries(scan)),
            "findings": [finding.as_dict() for finding in scan.findings],
        }
        if not database.exists():
            return base
        try:
            uri = database.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("integrity check failed")
                metadata = self._read_metadata(connection)
                indexed_versions = _metadata_versions(metadata)
                ddl_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                schema_version = connection.execute(
                    "SELECT value FROM schema_metadata WHERE key='projection_contract_version'"
                ).fetchone()
                indexed_state = self._read_scan_state(connection)
                base["counts"] = self._counts(connection)
                base["changed_paths"] = _changed_paths(scan, indexed_state)
                base["versions"] = {"runtime": _runtime_versions(), "index": indexed_versions}
                base["snapshot"] = {
                    "current": current_snapshot,
                    "indexed": metadata.get("source_snapshot"),
                }
                if (
                    indexed_versions != _runtime_versions()
                    or ddl_version != PROJECTION_VERSION
                    or schema_version is None
                    or schema_version[0] != str(PROJECTION_VERSION)
                ):
                    base["state"] = "incompatible"
                elif not scan.healthy or metadata.get("source_snapshot") != current_snapshot:
                    base["state"] = "stale"
                else:
                    base["state"] = "fresh"
        except (OSError, sqlite3.Error, KeyError):
            base["state"] = "corrupt"
            base["versions"] = {"runtime": _runtime_versions(), "index": None}
            base["snapshot"] = {"current": current_snapshot, "indexed": None}
        return base

    def _raise_for_state(self, state: str) -> None:
        mapping = {
            "missing": ("INDEX_NOT_FOUND", "index does not exist"),
            "incompatible": ("INDEX_INCOMPATIBLE", "index versions are incompatible"),
            "corrupt": ("INDEX_CORRUPT", "index cannot be validated"),
            "stale": ("INDEX_SOURCE_CHANGED", "index is stale"),
        }
        if state in mapping:
            code, message = mapping[state]
            raise DomainError(code, message)

    def build(self, vault: Vault, *, rebuild: bool = False) -> dict[str, object]:
        operation = "rebuild" if rebuild else "build"
        with self._writer_lock(vault):
            initial = scan_vault(vault)
            if not initial.healthy:
                raise DomainError("INDEX_SOURCE_INVALID", "Vault scan contains error findings")
            database = self.database_path(vault)
            changed = sorted(path for path, _checksum in _snapshot_entries(initial))
            if rebuild or not database.exists():
                self._full_rebuild(vault, initial)
            else:
                status = self.status(vault)
                state = str(status["state"])
                changed = cast(list[str], status["changed_paths"])
                if state in {"incompatible", "corrupt"}:
                    self._raise_for_state(state)
                if state == "stale":
                    self._incremental_update(vault, initial, changed)
            result = self.status(vault)
            result["operation"] = operation
            result["changed_paths"] = changed
            return result

    def _full_rebuild(self, vault: Vault, scan: ScanResult) -> None:
        database = self.database_path(vault)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".kb-index-", suffix=".sqlite", dir=database.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        temporary.unlink(missing_ok=True)
        try:
            with closing(sqlite3.connect(temporary)) as connection:
                connection.executescript(self._ddl_reader("schemas/v2/sqlite-projection-v2.sql"))
                self._replace_rows(connection, scan)
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise sqlite3.IntegrityError("foreign key check failed")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("integrity check failed")
                connection.commit()
            if snapshot_hash(scan_vault(vault)) != snapshot_hash(scan):
                raise DomainError("INDEX_SOURCE_CHANGED", "Vault changed during index rebuild")
            os.replace(temporary, database)
        except DomainError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise DomainError("INDEX_CORRUPT", "index rebuild failed") from error
        finally:
            temporary.unlink(missing_ok=True)

    def _incremental_update(self, vault: Vault, scan: ScanResult, changed_paths: list[str]) -> None:
        database = self.database_path(vault)
        try:
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                old_objects = dict(connection.execute("SELECT path,id FROM objects"))
                new_objects = {item.path: item for item in scan.objects.values()}
                changed = set(changed_paths)
                old_ids = {old_objects[path] for path in changed if path in old_objects}
                new_ids = {
                    str(new_objects[path].document.object.id)
                    for path in changed
                    if path in new_objects
                }
                current_ids = {str(object_id) for object_id in scan.objects}
                deleted_ids = old_ids - current_ids
                upsert_ids = new_ids

                for object_id in sorted(deleted_ids):
                    connection.execute("DELETE FROM fts_segments WHERE object_id=?", (object_id,))
                    connection.execute("DELETE FROM objects WHERE id=?", (object_id,))

                scanned_by_id = {
                    str(object_id): scanned for object_id, scanned in scan.objects.items()
                }
                existing_ids = (
                    {
                        str(row[0])
                        for row in connection.execute(
                            "SELECT id FROM objects WHERE id IN ({})".format(
                                ",".join("?" for _value in upsert_ids)
                            ),
                            sorted(upsert_ids),
                        )
                    }
                    if upsert_ids
                    else set()
                )
                for object_id in sorted(existing_ids):
                    connection.execute(
                        "UPDATE objects SET path=? WHERE id=?",
                        (f"__index_tmp__/{object_id}", object_id),
                    )
                for object_id in sorted(upsert_ids):
                    connection.execute("DELETE FROM fts_segments WHERE object_id=?", (object_id,))
                    connection.execute("DELETE FROM sections WHERE object_id=?", (object_id,))
                    connection.execute(
                        "DELETE FROM type_transitions WHERE object_id=?", (object_id,)
                    )
                    connection.execute("DELETE FROM object_tags WHERE object_id=?", (object_id,))
                    scanned = scanned_by_id[object_id]
                    if object_id in existing_ids:
                        self._update_object(connection, scanned)
                    else:
                        self._insert_object(connection, scanned)
                    obj = scanned.document.object
                    self._insert_content(
                        connection,
                        scanned.document,
                        obj.title,
                        getattr(obj, "tags", ()),
                    )

                relation_prefix = vault.config.relations.rstrip("/") + "/"
                relation_ids = {
                    Path(path).stem for path in changed if path.startswith(relation_prefix)
                }
                relation_ids.update(
                    str(from_id)
                    for from_id, scanned in scan.relation_shards.items()
                    if scanned.path in changed
                )
                for from_id in sorted(relation_ids):
                    connection.execute("DELETE FROM relations WHERE from_id=?", (from_id,))
                    shard = next(
                        (item for key, item in scan.relation_shards.items() if str(key) == from_id),
                        None,
                    )
                    if shard is not None:
                        self._insert_relation_shard(connection, shard)

                connection.execute(
                    "DELETE FROM tags WHERE NOT EXISTS "
                    "(SELECT 1 FROM object_tags WHERE object_tags.tag=tags.tag)"
                )
                now = datetime.now(UTC).isoformat()
                for path in sorted(changed):
                    connection.execute("DELETE FROM scan_state WHERE path=?", (path,))
                current_entries = dict(_snapshot_entries(scan))
                connection.executemany(
                    "INSERT INTO scan_state(path,checksum,modified_at,scanned_at) "
                    "VALUES (?,?,NULL,?)",
                    [
                        (path, current_entries[path], now)
                        for path in sorted(changed)
                        if path in current_entries
                    ],
                )
                connection.execute(
                    "UPDATE index_metadata SET value=? WHERE key='source_snapshot'",
                    (snapshot_hash(scan),),
                )
                connection.execute(
                    "UPDATE index_metadata SET value=? WHERE key='last_successful_build'",
                    (now,),
                )
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise sqlite3.IntegrityError("foreign key check failed")
                if snapshot_hash(scan_vault(vault)) != snapshot_hash(scan):
                    raise DomainError("INDEX_SOURCE_CHANGED", "Vault changed during index build")
                connection.commit()
        except DomainError:
            raise
        except sqlite3.Error as error:
            raise DomainError("INDEX_CORRUPT", "index update failed") from error

    def _replace_rows(self, connection: sqlite3.Connection, scan: ScanResult) -> None:
        connection.execute("PRAGMA foreign_keys = ON")
        ordered = sorted(
            scan.objects.values(), key=lambda item: (item.path, str(item.document.object.id))
        )
        for scanned in ordered:
            self._insert_object(connection, scanned)
        for scanned in ordered:
            obj = scanned.document.object
            self._insert_content(connection, scanned.document, obj.title, getattr(obj, "tags", ()))
        for relation_scanned in sorted(scan.relation_shards.values(), key=lambda item: item.path):
            self._insert_relation_shard(connection, relation_scanned)
        now = datetime.now(UTC).isoformat()
        connection.executemany(
            "INSERT INTO scan_state(path,checksum,modified_at,scanned_at) VALUES (?,?,NULL,?)",
            [(path, checksum, now) for path, checksum in _snapshot_entries(scan)],
        )
        metadata = {f"{name}_version": str(value) for name, value in _runtime_versions().items()}
        metadata.update(source_snapshot=snapshot_hash(scan), last_successful_build=now)
        connection.executemany("INSERT INTO index_metadata VALUES (?,?)", sorted(metadata.items()))

    @staticmethod
    def _object_row(scanned: Any) -> tuple[object, ...]:
        obj = scanned.document.object
        subtype: str | None = None
        workflow: str | None = None
        maturity: str | None = None
        review: str | None = None
        if isinstance(obj, Source):
            subtype, workflow = obj.source_type.value, obj.workflow_stage.value
        elif isinstance(obj, Note):
            subtype, maturity = obj.note_type.value, obj.maturity.value
        elif isinstance(obj, AIArtifact):
            subtype, review = obj.artifact_type.value, obj.review_status.value
        updated = getattr(obj, "updated", None)
        return (
            str(obj.id),
            obj.id.kind.value,
            subtype,
            scanned.path,
            obj.title,
            obj.visibility.value,
            obj.record_status.value,
            workflow,
            maturity,
            review,
            obj.created.isoformat(),
            updated.isoformat() if updated is not None else None,
            scanned.checksum,
        )

    def _insert_object(self, connection: sqlite3.Connection, scanned: Any) -> None:
        connection.execute(
            "INSERT INTO objects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._object_row(scanned),
        )
        self._insert_object_dependents(connection, scanned)

    def _update_object(self, connection: sqlite3.Connection, scanned: Any) -> None:
        row = self._object_row(scanned)
        connection.execute(
            "UPDATE objects SET kind=?,subtype=?,path=?,title=?,visibility=?,record_status=?,"
            "workflow_stage=?,maturity=?,review_status=?,created_at=?,updated_at=?,checksum=? "
            "WHERE id=?",
            (*row[1:], row[0]),
        )
        self._insert_object_dependents(connection, scanned)

    @staticmethod
    def _insert_object_dependents(connection: sqlite3.Connection, scanned: Any) -> None:
        obj = scanned.document.object
        for tag in sorted(getattr(obj, "tags", ())):
            connection.execute("INSERT OR IGNORE INTO tags(tag) VALUES (?)", (tag,))
            connection.execute("INSERT INTO object_tags VALUES (?,?)", (str(obj.id), tag))
        if isinstance(obj, Note):
            for ordinal, transition in enumerate(obj.type_history):
                connection.execute(
                    "INSERT INTO type_transitions VALUES (?,?,?,?,?,?,?)",
                    (
                        str(obj.id),
                        ordinal,
                        transition.from_type.value,
                        transition.to_type.value,
                        transition.changed_at.isoformat(),
                        transition.actor.type.value,
                        transition.actor.id,
                    ),
                )

    @staticmethod
    def _insert_relation_shard(connection: sqlite3.Connection, scanned: Any) -> None:
        for relation in sorted(scanned.shard.relations, key=lambda item: item.canonical_key):
            connection.execute(
                "INSERT INTO relations VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(scanned.shard.from_id),
                    str(relation.to_id),
                    str(relation.to_section_id or ""),
                    relation.relation_type.value,
                    canonical_json(locator_data(relation.locator)) if relation.locator else "",
                    relation.reason,
                    relation.created_at.isoformat(),
                    relation.actor.type.value,
                    relation.actor.id,
                ),
            )

    def _insert_content(
        self, connection: sqlite3.Connection, document: Any, title: str, tags: tuple[str, ...]
    ) -> None:
        obj = document.object
        object_id = str(obj.id)
        if isinstance(document.body, NoteBody):
            for section_ordinal, section in enumerate(document.body.sections):
                section_id = str(section.section_id)
                connection.execute(
                    "INSERT INTO sections VALUES (?,?,?,?,?)",
                    (object_id, section_id, section.role.value, section.heading, section_ordinal),
                )
                for block_ordinal, block in enumerate(section.blocks):
                    role = section.role.value
                    artifact_id = str(block.artifact_id) if isinstance(block, AIBlock) else None
                    citations = block.citations if isinstance(block, FactBlock) else ()
                    self._insert_segment(
                        connection,
                        object_id,
                        section_id,
                        role,
                        block.text,
                        block_ordinal,
                        artifact_id,
                        citations,
                        title,
                        tags,
                    )
        else:
            role = (
                "source"
                if isinstance(obj, Source)
                else "snippet"
                if isinstance(obj, Snippet)
                else "ai"
            )
            connection.execute(
                "INSERT INTO sections VALUES (?,?,?,?,?)",
                (object_id, BODY_SECTION, role, BODY_SECTION, 0),
            )
            self._insert_segment(
                connection, object_id, BODY_SECTION, role, document.body, 0, None, (), title, tags
            )

    def _insert_segment(
        self,
        connection: sqlite3.Connection,
        object_id: str,
        section_id: str,
        role: str,
        text: str,
        ordinal: int,
        artifact_id: str | None,
        citations: tuple[Any, ...],
        title: str,
        tags: tuple[str, ...],
    ) -> None:
        identifier = segment_id(object_id, section_id, ordinal)
        connection.execute(
            "INSERT INTO segments VALUES (?,?,?,?,?,?,?)",
            (identifier, object_id, section_id, role, text, ordinal, artifact_id),
        )
        for citation_ordinal, citation in enumerate(citations):
            connection.execute(
                "INSERT INTO citations VALUES (?,?,?,?)",
                (
                    identifier,
                    citation_ordinal,
                    str(citation.source_id),
                    canonical_json(locator_data(citation.locator)),
                ),
            )
        connection.execute(
            "INSERT INTO fts_segments VALUES (?,?,?,?,?,?,?,?,?)",
            (
                " ".join(tokenize(title)),
                " ".join(tokenize(text)),
                " ".join(tokenize(" ".join(tags))),
                identifier,
                object_id,
                section_id,
                role,
                str(
                    connection.execute(
                        "SELECT visibility FROM objects WHERE id=?", (object_id,)
                    ).fetchone()[0]
                ),
                str(
                    connection.execute(
                        "SELECT record_status FROM objects WHERE id=?", (object_id,)
                    ).fetchone()[0]
                ),
            ),
        )

    def refresh_if_present(self, vault: Vault) -> bool:
        if not self.database_path(vault).exists():
            return False
        status = self.status(vault)
        if status["state"] == "incompatible" or status["state"] == "corrupt":
            return False
        self.build(vault)
        return True

    def search(
        self,
        vault: Vault,
        query: str,
        filters: SearchFilters,
        scope: ContextScope,
        limit: int,
    ) -> tuple[SearchHit, ...]:
        if not 1 <= limit <= 200:
            raise DomainError("SEARCH_QUERY_INVALID", "limit must be between 1 and 200")
        if filters.kind not in (None, "source", "note", "snippet", "ai_artifact"):
            raise DomainError("SEARCH_QUERY_INVALID", "unsupported object kind filter")
        if filters.role not in (None, "source", "human", "fact", "ai", "evolution", "snippet"):
            raise DomainError("SEARCH_QUERY_INVALID", "unsupported role filter")
        if scope is ContextScope.PUBLIC_SAFE and (
            filters.kind == "ai_artifact" or filters.role == "ai"
        ):
            raise DomainError("SEARCH_QUERY_INVALID", "AI search is trusted-local only")
        match = literal_fts_query(query)
        status = self.status(vault)
        if status["findings"]:
            raise DomainError("INDEX_SOURCE_INVALID", "Vault scan contains error findings")
        self._raise_for_state(str(status["state"]))
        clauses = ["fts_segments MATCH ?"]
        parameters: list[object] = [match]
        values = {
            "kind": filters.kind,
            "subtype": filters.subtype,
            "visibility": filters.visibility,
            "record_status": filters.record_status,
            "workflow_stage": filters.workflow_stage,
            "maturity": filters.maturity,
            "review_status": filters.review_status,
            "provenance_role": filters.role,
        }
        for column, value in values.items():
            if value is not None:
                clauses.append(f"{('s.' if column == 'provenance_role' else 'o.')}{column} = ?")
                parameters.append(value)
        if filters.record_status is None:
            clauses.append("o.record_status = 'active'")
        if filters.role is None:
            if filters.kind == "ai_artifact":
                clauses.append("s.provenance_role = 'ai'")
            else:
                clauses.append("s.provenance_role IN ('source','human','fact','snippet')")
        if scope is ContextScope.PUBLIC_SAFE:
            clauses.extend(
                (
                    "o.visibility = 'public'",
                    "o.record_status = 'active'",
                    "s.provenance_role != 'ai'",
                )
            )
        for tag in filters.tags:
            clauses.append(
                "EXISTS (SELECT 1 FROM object_tags ot WHERE ot.object_id=o.id AND ot.tag=?)"
            )
            parameters.append(tag)
        sql = f"""
            SELECT s.segment_id,s.object_id,o.kind,o.subtype,o.path,o.title,s.section_id,
                   s.provenance_role,s.ordinal,s.text,bm25(fts_segments),o.visibility,o.record_status
            FROM fts_segments
            JOIN segments s ON s.segment_id=fts_segments.segment_id
            JOIN objects o ON o.id=s.object_id
            WHERE {" AND ".join(clauses)}
            ORDER BY bm25(fts_segments),s.object_id,
                     CASE WHEN s.section_id=? THEN '' ELSE s.section_id END,s.ordinal
            LIMIT ?
        """
        parameters.extend((BODY_SECTION, -1 if scope is ContextScope.PUBLIC_SAFE else limit))
        database = self.database_path(vault)
        try:
            with closing(sqlite3.connect(database)) as connection:
                rows = connection.execute(sql, parameters).fetchall()
                hits: list[SearchHit] = []
                scan = scan_vault(vault) if scope is ContextScope.PUBLIC_SAFE else None
                for row in rows:
                    tags = tuple(
                        value[0]
                        for value in connection.execute(
                            "SELECT tag FROM object_tags WHERE object_id=? ORDER BY tag", (row[1],)
                        )
                    )
                    citations = tuple(
                        {"source_id": value[0], "locator": json.loads(value[1])}
                        for value in connection.execute(
                            "SELECT source_id,locator FROM citations "
                            "WHERE segment_id=? ORDER BY ordinal",
                            (row[0],),
                        )
                    )
                    if scan is not None and not self._public_safe(scan, row[1], row[7], citations):
                        continue
                    hits.append(
                        SearchHit(
                            segment_id=row[0],
                            object_id=row[1],
                            kind=row[2],
                            subtype=row[3],
                            path=row[4],
                            title=row[5],
                            section_id=None if row[6] == BODY_SECTION else row[6],
                            role=row[7],
                            ordinal=row[8],
                            text=row[9],
                            score=float(row[10]),
                            tags=tags,
                            visibility=row[11],
                            record_status=row[12],
                            citations=citations,
                        )
                    )
                    if len(hits) == limit:
                        break
                latest = scan_vault(vault)
                if not latest.healthy:
                    raise DomainError("INDEX_SOURCE_INVALID", "Vault scan contains error findings")
                indexed_snapshot = cast(dict[str, object], status["snapshot"])["indexed"]
                if snapshot_hash(latest) != indexed_snapshot:
                    raise DomainError("INDEX_SOURCE_CHANGED", "index became stale during query")
                return tuple(hits)
        except sqlite3.Error as error:
            raise DomainError("INDEX_CORRUPT", "index query failed") from error

    @staticmethod
    def _public_safe(
        scan: ScanResult, object_id: str, role: str, citations: tuple[dict[str, object], ...]
    ) -> bool:
        scanned = next(
            (value for key, value in scan.objects.items() if str(key) == object_id), None
        )
        if scanned is None:
            return False
        obj = scanned.document.object
        if obj.visibility is not Visibility.PUBLIC or obj.record_status is not RecordStatus.ACTIVE:
            return False
        if role == "ai" or isinstance(obj, AIArtifact):
            return False
        if role == "fact" and not citations:
            return False
        if isinstance(obj, Source):
            if obj.source_type.value == "web" and obj.snapshot_ref is None:
                return False
            if obj.source_type.value == "oss" and obj.license == "NOASSERTION":
                return False
        sources = {str(key): value.document.object for key, value in scan.objects.items()}
        for citation in citations:
            source = sources.get(str(citation["source_id"]))
            if (
                not isinstance(source, Source)
                or source.visibility is not Visibility.PUBLIC
                or source.record_status is not RecordStatus.ACTIVE
            ):
                return False
            if source.source_type.value == "web" and source.snapshot_ref is None:
                return False
            if source.source_type.value == "oss" and source.license == "NOASSERTION":
                return False
            try:
                locator = parse_locator(citation["locator"])
            except (DomainError, KeyError, TypeError):
                return False
            if locator_mismatched_fields(locator, source):
                return False
        if isinstance(obj, Snippet):
            source = sources.get(str(obj.source_id))
            return (
                obj.publication_approved
                and obj.license != "NOASSERTION"
                and isinstance(source, Source)
                and source.visibility is Visibility.PUBLIC
                and source.record_status is RecordStatus.ACTIVE
                and source.source_type.value == "oss"
                and source.license != "NOASSERTION"
                and (obj.repository_host, obj.repository_path, obj.commit)
                == (source.repository_host, source.repository_path, source.commit)
            )
        return True
