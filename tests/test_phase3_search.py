from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from knowlume.adapters.contract_v2 import (
    parse_object_document,
    parse_relation_shard,
    render_object_document,
    render_relation_shard,
)
from knowlume.adapters.filesystem import FilesystemVault, checksum_file
from knowlume.adapters.sqlite_projection import SQLiteProjection
from knowlume.application.indexing import IndexRefreshService
from knowlume.application.query import QueryService, get_object, grep_vault
from knowlume.application.scanning import scan_vault
from knowlume.domain.models import (
    FactBlock,
    HumanBlock,
    Note,
    NoteBody,
    PaperLocator,
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
from knowlume.domain.values import (
    DomainError,
    ObjectId,
    RecordStatus,
    RelationType,
    SectionRole,
    Visibility,
)
from knowlume.ports.vault import Vault

ROOT = Path(__file__).resolve().parents[1]


def _vault(tmp_path: Path) -> tuple[Vault, str]:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "vault", (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
    )
    source = ROOT / "tests/fixtures/v2/valid/idea-note.md"
    target = vault.path("notes") / "ideas" / source.name
    shutil.copyfile(source, target)
    object_id = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
    return vault, object_id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ＡＢC Straße １２", ("abc", "strasse", "12")),
        ("知识库", ("知", "识", "库", "知识", "识库")),
        ("AI知识 2.0", ("ai", "知", "识", "知识", "2", "0")),
        ("!?", ()),
        ("\U00020000\U00020001", ("\U00020000", "\U00020001", "\U00020000\U00020001")),
    ],
)
def test_tokenizer_v1_golden_cases(text: str, expected: tuple[str, ...]) -> None:
    assert tokenize(text) == expected


def test_literal_query_and_segment_identity_are_deterministic() -> None:
    assert literal_fts_query('alpha OR "beta"') == '"alpha" AND "or" AND "beta"'
    assert segment_id("note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2", "sec_human", 0) == segment_id(
        "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2", "sec_human", 0
    )
    with pytest.raises(DomainError, match="query"):
        literal_fts_query(" -! ")


def test_grep_and_get_do_not_create_an_index(tmp_path: Path) -> None:
    vault, object_id = _vault(tmp_path)
    grep = grep_vault(vault, "Knowledge", 20)
    result = get_object(vault, object_id)
    assert grep["count"]
    assert result["object_id"] == object_id
    assert result["path"] == "notes/ideas/idea-note.md"
    assert not (vault.path("state") / "kb.sqlite").exists()


def test_grep_reports_source_columns_after_nfkc_casefold_expansion(tmp_path: Path) -> None:
    vault, _object_id = _vault(tmp_path)
    path = vault.path("notes") / "ideas" / "idea-note.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Knowledge tools", "Straße Knowledge tools"),
        encoding="utf-8",
    )

    result = grep_vault(vault, "knowledge")

    assert result["count"] == 1
    assert cast(list[dict[str, object]], result["hits"])[0]["column"] == 8


def test_rebuild_search_context_and_status_lifecycle(tmp_path: Path) -> None:
    vault, object_id = _vault(tmp_path)
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    missing = projection.status(vault)
    assert missing["state"] == "missing"
    built = projection.build(vault, rebuild=True)
    assert built["state"] == "fresh"
    service = QueryService(projection)
    result = service.search(vault, "Knowledge", SearchFilters(), ContextScope.TRUSTED_LOCAL, 20)
    assert result["count"] == 1
    hit = result["hits"][0]  # type: ignore[index]
    assert hit["object_id"] == object_id
    assert hit["section_id"] == "sec_core_idea"
    context = service.context(vault, "Knowledge", ContextScope.TRUSTED_LOCAL, 20, 12_000)
    assert context["groups"]["human_notes"]  # type: ignore[index]
    database = vault.path("state") / "kb.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        first = connection.execute("SELECT segment_id FROM segments ORDER BY segment_id").fetchall()
    projection.build(vault, rebuild=True)
    with closing(sqlite3.connect(database)) as connection:
        second = connection.execute(
            "SELECT segment_id FROM segments ORDER BY segment_id"
        ).fetchall()
    assert first == second
    path = vault.path("notes") / "ideas" / "idea-note.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    assert projection.status(vault)["state"] == "stale"
    stale_checksum = checksum_file(database)
    with pytest.raises(DomainError) as stale_search:
        service.search(vault, "Knowledge", SearchFilters(), ContextScope.TRUSTED_LOCAL, 20)
    assert stale_search.value.code == "INDEX_SOURCE_CHANGED"
    assert checksum_file(database) == stale_checksum


def _logical_rows(database: Path) -> dict[str, list[tuple[object, ...]]]:
    tables = (
        "objects",
        "type_transitions",
        "relations",
        "sections",
        "segments",
        "citations",
        "tags",
        "object_tags",
    )
    with closing(sqlite3.connect(database)) as connection:
        result = {
            table: sorted(connection.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
            for table in tables
        }
        result["scan_state"] = connection.execute(
            "SELECT path,checksum,modified_at FROM scan_state ORDER BY path"
        ).fetchall()
        return result


def _rich_vault(tmp_path: Path) -> Vault:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "rich-vault",
        (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8"),
    )
    copies = (
        ("paper-source.md", vault.path("sources") / "papers"),
        ("literature-note.md", vault.path("notes") / "literature"),
        ("idea-note.md", vault.path("notes") / "ideas"),
    )
    for name, target in copies:
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "tests/fixtures/v2/valid" / name, target / name)
    relation = ROOT / "tests/fixtures/v2/valid/relations/note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2.yaml"
    shutil.copyfile(relation, vault.path("relations") / relation.name)
    return vault


def test_incremental_refresh_matches_rebuild_and_absence_is_a_noop(tmp_path: Path) -> None:
    vault, _object_id = _vault(tmp_path)
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    assert projection.refresh_if_present(vault) is False
    assert not projection.database_path(vault).exists()
    projection.build(vault)
    path = vault.path("notes") / "ideas" / "idea-note.md"
    text = path.read_text(encoding="utf-8").replace(
        "Knowledge tools", "Deterministic knowledge tools"
    )
    path.write_text(text, encoding="utf-8")
    assert projection.refresh_if_present(vault) is True
    assert projection.status(vault)["state"] == "fresh"
    incremental = _logical_rows(projection.database_path(vault))
    projection.build(vault, rebuild=True)
    rebuilt = _logical_rows(projection.database_path(vault))
    assert incremental == rebuilt


def test_incremental_change_sets_cover_relation_delete_move_tag_role_and_citation(
    tmp_path: Path,
) -> None:
    vault = _rich_vault(tmp_path)
    ddl = (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(encoding="utf-8")
    projection = SQLiteProjection(ddl_reader=lambda _name: ddl)
    projection.build(vault)
    database = projection.database_path(vault)
    idea_id = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
    literature_id = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2"

    with closing(sqlite3.connect(database)) as connection:
        idea_rowid = connection.execute(
            "SELECT rowid FROM objects WHERE id=?", (idea_id,)
        ).fetchone()[0]
        idea_segment_rowid = connection.execute(
            "SELECT rowid FROM segments WHERE object_id=?", (idea_id,)
        ).fetchone()[0]
        relation_before = connection.execute(
            "SELECT rowid FROM relations WHERE from_id=?", (literature_id,)
        ).fetchone()[0]
    before_noop = checksum_file(database)
    noop = projection.build(vault)
    assert noop["changed_paths"] == []
    assert checksum_file(database) == before_noop

    new_fixture = ROOT / "tests/fixtures/v2/valid/public-idea-note.md"
    new_path = vault.path("notes") / "ideas" / new_fixture.name
    shutil.copyfile(new_fixture, new_path)
    create_build = projection.build(vault)
    assert create_build["changed_paths"] == ["notes/ideas/public-idea-note.md"]
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM objects WHERE id=?",
                ("note_01JSTAG7N9Q3V5X8Y2Z4A6B8D1",),
            ).fetchone()[0]
            == 1
        )
    new_path.unlink()
    projection.build(vault)

    literature_path = vault.path("notes") / "literature" / "literature-note.md"
    literature = parse_object_document(literature_path.read_text(encoding="utf-8"))
    assert isinstance(literature.object, Note)
    literature = replace(
        literature,
        object=replace(literature.object, tags=(*literature.object.tags, "incremental")),
    )
    literature_path.write_text(render_object_document(literature), encoding="utf-8")
    tag_build = projection.build(vault)
    assert tag_build["changed_paths"] == ["notes/literature/literature-note.md"]
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT rowid FROM objects WHERE id=?", (idea_id,)).fetchone()[0]
            == idea_rowid
        )
        assert (
            connection.execute(
                "SELECT rowid FROM segments WHERE object_id=?", (idea_id,)
            ).fetchone()[0]
            == idea_segment_rowid
        )
        assert (
            connection.execute(
                "SELECT rowid FROM relations WHERE from_id=?", (literature_id,)
            ).fetchone()[0]
            == relation_before
        )

    relation_path = vault.path("relations") / f"{literature_id}.yaml"
    relation_fixture = ROOT / "tests/fixtures/v2/valid/relations" / f"{literature_id}.yaml"
    optional_shard = parse_relation_shard(relation_fixture.read_text(encoding="utf-8"))
    optional_shard = replace(
        optional_shard,
        from_id=ObjectId(idea_id),
        relations=(
            replace(
                optional_shard.relations[0],
                to_id=ObjectId(literature_id),
                relation_type=RelationType.SUPPORTS,
                locator=None,
            ),
        ),
    )
    optional_path = vault.path("relations") / f"{idea_id}.yaml"
    optional_path.write_text(render_relation_shard(optional_shard), encoding="utf-8")
    create_relation = projection.build(vault)
    assert create_relation["changed_paths"] == [f"relations/{idea_id}.yaml"]
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM relations WHERE from_id=?", (idea_id,)
            ).fetchone()[0]
            == 1
        )
    optional_path.unlink()
    delete_relation = projection.build(vault)
    assert delete_relation["changed_paths"] == [f"relations/{idea_id}.yaml"]
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM relations WHERE from_id=?", (idea_id,)
            ).fetchone()[0]
            == 0
        )

    shard = parse_relation_shard(relation_path.read_text(encoding="utf-8"))
    shard = replace(shard, relations=(replace(shard.relations[0], reason="incremental"),))
    relation_path.write_text(render_relation_shard(shard), encoding="utf-8")
    relation_build = projection.build(vault)
    assert relation_build["changed_paths"] == [f"relations/{literature_id}.yaml"]
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT rowid FROM objects WHERE id=?", (idea_id,)).fetchone()[0]
            == idea_rowid
        )
        assert (
            connection.execute(
                "SELECT reason FROM relations WHERE from_id=?", (literature_id,)
            ).fetchone()[0]
            == "incremental"
        )

    literature = parse_object_document(literature_path.read_text(encoding="utf-8"))
    assert isinstance(literature.body, NoteBody)
    fact_section = literature.body.sections[0]
    fact = fact_section.blocks[0]
    assert isinstance(fact, FactBlock)
    citation = fact.citations[0]
    assert isinstance(citation.locator, PaperLocator)
    changed_fact = replace(
        fact,
        citations=(replace(citation, locator=replace(citation.locator, page=5)),),
    )
    changed_body = replace(
        literature.body,
        sections=(replace(fact_section, blocks=(changed_fact,)), *literature.body.sections[1:]),
    )
    literature_path.write_text(
        render_object_document(replace(literature, body=changed_body)), encoding="utf-8"
    )
    projection.build(vault)
    with closing(sqlite3.connect(database)) as connection:
        locator = connection.execute(
            "SELECT locator FROM citations c JOIN segments s USING(segment_id) WHERE s.object_id=?",
            (literature_id,),
        ).fetchone()[0]
    assert '"page":5' in locator

    literature = parse_object_document(literature_path.read_text(encoding="utf-8"))
    assert isinstance(literature.body, NoteBody)
    fact_section = literature.body.sections[0]
    fact = fact_section.blocks[0]
    assert isinstance(fact, FactBlock)
    humanized = replace(
        fact_section,
        role=SectionRole.HUMAN,
        blocks=(HumanBlock(fact.text),),
    )
    role_body = replace(
        literature.body,
        sections=(humanized, *literature.body.sections[1:]),
    )
    literature_path.write_text(
        render_object_document(replace(literature, body=role_body)), encoding="utf-8"
    )
    projection.build(vault)
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute(
                "SELECT role FROM sections WHERE object_id=? ORDER BY ordinal", (literature_id,)
            ).fetchone()[0]
            == "human"
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM citations c JOIN segments s USING(segment_id) "
                "WHERE s.object_id=?",
                (literature_id,),
            ).fetchone()[0]
            == 0
        )

    moved = literature_path.with_name("renamed-literature.md")
    literature_path.rename(moved)
    move_build = projection.build(vault)
    assert move_build["changed_paths"] == [
        "notes/literature/literature-note.md",
        "notes/literature/renamed-literature.md",
    ]
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT path FROM objects WHERE id=?", (literature_id,)).fetchone()[
                0
            ]
            == "notes/literature/renamed-literature.md"
        )

    idea_path = vault.path("notes") / "ideas" / "idea-note.md"
    idea_path.unlink()
    delete_build = projection.build(vault)
    assert delete_build["changed_paths"] == ["notes/ideas/idea-note.md"]
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM objects WHERE id=?", (idea_id,)).fetchone()[0]
            == 0
        )

    incremental = _logical_rows(database)
    projection.build(vault, rebuild=True)
    assert _logical_rows(database) == incremental


def test_refresh_failure_is_a_stable_warning_after_durable_success(tmp_path: Path) -> None:
    vault, _object_id = _vault(tmp_path)

    class BrokenStore:
        def status(self, vault: Vault) -> dict[str, object]:
            return {}

        def build(self, vault: Vault, *, rebuild: bool = False) -> dict[str, object]:
            return {}

        def refresh_if_present(self, vault: Vault) -> bool:
            raise RuntimeError("private adapter detail")

    service = IndexRefreshService(BrokenStore())
    assert service.after_mutation(vault) == ("INDEX_REFRESH_FAILED",)
    assert service.after_mutation(vault, changed=False) == ()


def test_busy_invalid_and_concurrent_rebuilds_preserve_the_old_database(tmp_path: Path) -> None:
    vault, _object_id = _vault(tmp_path)
    ddl = (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(encoding="utf-8")
    projection = SQLiteProjection(ddl_reader=lambda _name: ddl)
    projection.build(vault, rebuild=True)
    database = projection.database_path(vault)
    baseline = checksum_file(database)

    lock = vault.path("state") / "locks" / "index.lock"
    lock.write_text("other", encoding="ascii")
    with pytest.raises(DomainError) as busy:
        projection.build(vault)
    assert busy.value.code == "INDEX_BUSY"
    assert checksum_file(database) == baseline
    lock.unlink()

    invalid = ROOT / "tests/fixtures/v2/invalid/missing-human-section.md"
    invalid_target = vault.path("notes") / "ideas" / invalid.name
    shutil.copyfile(invalid, invalid_target)
    with pytest.raises(DomainError) as source_invalid:
        projection.build(vault, rebuild=True)
    assert source_invalid.value.code == "INDEX_SOURCE_INVALID"
    assert checksum_file(database) == baseline
    invalid_target.unlink()

    durable = vault.path("notes") / "ideas" / "idea-note.md"

    def changing_reader(_name: str) -> str:
        durable.write_text(
            durable.read_text(encoding="utf-8") + "\nConcurrent edit.\n", encoding="utf-8"
        )
        return ddl

    changing = SQLiteProjection(ddl_reader=changing_reader)
    with pytest.raises(DomainError) as source_changed:
        changing.build(vault, rebuild=True)
    assert source_changed.value.code == "INDEX_SOURCE_CHANGED"
    assert checksum_file(database) == baseline


def test_rebuild_failures_are_atomic_and_clean_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, _object_id = _vault(tmp_path)
    ddl = (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(encoding="utf-8")
    projection = SQLiteProjection(ddl_reader=lambda _name: ddl)
    projection.build(vault, rebuild=True)
    database = projection.database_path(vault)
    baseline = checksum_file(database)
    temporary_pattern = ".kb-index-*.sqlite"

    malformed = SQLiteProjection(ddl_reader=lambda _name: "not valid sqlite ddl")
    with pytest.raises(DomainError) as invalid_ddl:
        malformed.build(vault, rebuild=True)
    assert invalid_ddl.value.code == "INDEX_CORRUPT"
    assert checksum_file(database) == baseline
    assert list(database.parent.glob(temporary_pattern)) == []

    def interrupted_reader(_name: str) -> str:
        raise KeyboardInterrupt

    interrupted = SQLiteProjection(ddl_reader=interrupted_reader)
    with pytest.raises(KeyboardInterrupt):
        interrupted.build(vault, rebuild=True)
    assert checksum_file(database) == baseline
    assert list(database.parent.glob(temporary_pattern)) == []

    def failed_replace(_source: object, _destination: object) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("knowlume.adapters.sqlite_projection.os.replace", failed_replace)
    with pytest.raises(DomainError) as replace_failure:
        projection.build(vault, rebuild=True)
    assert replace_failure.value.code == "INDEX_CORRUPT"
    assert checksum_file(database) == baseline
    assert list(database.parent.glob(temporary_pattern)) == []


def test_incompatible_index_requires_explicit_rebuild(tmp_path: Path) -> None:
    vault, _object_id = _vault(tmp_path)
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    projection.build(vault)
    with closing(sqlite3.connect(projection.database_path(vault))) as connection:
        connection.execute("UPDATE index_metadata SET value='99' WHERE key='tokenizer_version'")
        connection.commit()
    assert projection.status(vault)["state"] == "incompatible"
    incompatible_checksum = checksum_file(projection.database_path(vault))
    with pytest.raises(DomainError) as incompatible_search:
        QueryService(projection).search(
            vault, "Knowledge", SearchFilters(), ContextScope.TRUSTED_LOCAL, 20
        )
    assert incompatible_search.value.code == "INDEX_INCOMPATIBLE"
    assert checksum_file(projection.database_path(vault)) == incompatible_checksum
    with pytest.raises(DomainError) as incompatible:
        projection.build(vault)
    assert incompatible.value.code == "INDEX_INCOMPATIBLE"
    assert projection.build(vault, rebuild=True)["state"] == "fresh"


def test_projection_covers_every_phase3_object_shape_and_provenance_edge(
    tmp_path: Path,
) -> None:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "shape-vault",
        (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8"),
    )
    copies = (
        ("paper-source.md", vault.path("sources") / "papers"),
        ("web-source.md", vault.path("sources") / "web"),
        ("book-source.md", vault.path("sources") / "books"),
        ("oss-source.md", vault.path("sources") / "oss"),
        ("idea-note.md", vault.path("notes") / "ideas"),
        ("literature-note.md", vault.path("notes") / "literature"),
        ("synthesis-note.md", vault.path("notes") / "syntheses"),
        ("promoted-concept-note.md", vault.path("notes") / "concepts"),
        ("promoted-ai-artifact.md", vault.path("ai_artifacts")),
        ("unreviewed-ai-artifact.md", vault.path("ai_artifacts")),
        ("snippet.md", vault.path("snippets")),
    )
    for name, target in copies:
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "tests/fixtures/v2/valid" / name, target / name)
    for relation in (ROOT / "tests/fixtures/v2/valid/relations").glob("*.yaml"):
        shutil.copyfile(relation, vault.path("relations") / relation.name)

    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    scan = scan_vault(vault)
    assert scan.healthy, [finding.as_dict() for finding in scan.findings]
    result = projection.build(vault, rebuild=True)

    assert result["state"] == "fresh"
    assert result["counts"] == {
        "objects": 11,
        "relations": 4,
        "sections": 13,
        "segments": 13,
        "citations": 1,
    }
    with closing(sqlite3.connect(projection.database_path(vault))) as connection:
        assert dict(
            connection.execute("SELECT subtype,COUNT(*) FROM objects GROUP BY subtype")
        ) == {
            "book": 1,
            "concept": 1,
            "draft": 2,
            "idea": 1,
            "literature": 1,
            "oss": 1,
            "paper": 1,
            "synthesis": 1,
            "web": 1,
            None: 1,
        }
        assert dict(
            connection.execute(
                "SELECT provenance_role,COUNT(*) FROM segments GROUP BY provenance_role"
            )
        ) == {
            "ai": 3,
            "fact": 1,
            "human": 4,
            "snippet": 1,
            "source": 4,
        }
        assert connection.execute("SELECT COUNT(*) FROM type_transitions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM object_tags").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM scan_state").fetchone()[0] == 14
        assert (
            connection.execute(
                "SELECT ai_artifact_id FROM segments WHERE provenance_role='ai' "
                "AND object_id LIKE 'note_%'"
            ).fetchone()[0]
            == "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E0"
        )
        assert (
            connection.execute(
                "SELECT value FROM index_metadata WHERE key='source_snapshot'"
            ).fetchone()[0]
            == cast(dict[str, object], result["snapshot"])["indexed"]
        )


def test_filters_literal_queries_and_explicit_ai_policy(tmp_path: Path) -> None:
    vault, _object_id = _vault(tmp_path)
    copies = (
        ("paper-source.md", vault.path("sources") / "papers"),
        ("promoted-ai-artifact.md", vault.path("ai_artifacts")),
        ("promoted-concept-note.md", vault.path("notes") / "concepts"),
    )
    for name, target_root in copies:
        shutil.copyfile(ROOT / "tests/fixtures/v2/valid" / name, target_root / name)
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    projection.build(vault)
    service = QueryService(projection)
    filtered = service.search(
        vault,
        "Knowledge",
        SearchFilters(
            kind="note",
            subtype="idea",
            visibility="private",
            record_status="active",
            maturity="seed",
            tags=("idea",),
            role="human",
        ),
        ContextScope.TRUSTED_LOCAL,
        20,
    )
    assert filtered["count"] == 1
    assert (
        service.search(
            vault,
            "Knowledge OR missing",
            SearchFilters(),
            ContextScope.TRUSTED_LOCAL,
            20,
        )["count"]
        == 0
    )
    assert (
        service.search(vault, "Candidate", SearchFilters(), ContextScope.TRUSTED_LOCAL, 20)["count"]
        == 0
    )
    ai_note = service.search(
        vault,
        "Candidate",
        SearchFilters(role="ai"),
        ContextScope.TRUSTED_LOCAL,
        20,
    )
    artifact = service.search(
        vault,
        "Candidate",
        SearchFilters(kind="ai_artifact"),
        ContextScope.TRUSTED_LOCAL,
        20,
    )
    assert ai_note["count"] == 2
    assert artifact["count"] == 1
    with pytest.raises(DomainError) as public_ai:
        service.search(
            vault,
            "Candidate",
            SearchFilters(role="ai"),
            ContextScope.PUBLIC_SAFE,
            20,
        )
    assert public_ai.value.code == "SEARCH_QUERY_INVALID"
    context = service.context(vault, "Candidate", ContextScope.TRUSTED_LOCAL, 20, 12_000)
    groups = cast(dict[str, list[dict[str, Any]]], context["groups"])
    assert all(not items for items in groups.values())


def test_fact_search_preserves_complete_citation_order(tmp_path: Path) -> None:
    vault = _rich_vault(tmp_path)
    literature_path = vault.path("notes") / "literature" / "literature-note.md"
    document = parse_object_document(literature_path.read_text(encoding="utf-8"))
    assert isinstance(document.body, NoteBody)
    section = document.body.sections[0]
    fact = section.blocks[0]
    assert isinstance(fact, FactBlock)
    citation = fact.citations[0]
    assert isinstance(citation.locator, PaperLocator)
    two_citations = replace(
        fact,
        citations=(
            citation,
            replace(citation, locator=replace(citation.locator, page=5)),
        ),
    )
    literature_path.write_text(
        render_object_document(
            replace(
                document,
                body=replace(
                    document.body,
                    sections=(
                        replace(section, blocks=(two_citations,)),
                        *document.body.sections[1:],
                    ),
                ),
            )
        ),
        encoding="utf-8",
    )
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    projection.build(vault)

    result = QueryService(projection).search(
        vault,
        "Transformer uses",
        SearchFilters(role="fact"),
        ContextScope.TRUSTED_LOCAL,
        20,
    )

    hits = cast(list[dict[str, object]], result["hits"])
    citations = cast(list[dict[str, object]], hits[0]["citations"])
    assert [cast(dict[str, object], item["locator"])["page"] for item in citations] == [4, 5]


def test_public_safe_context_retains_safe_human_opinion_and_reports_private_exclusion(
    tmp_path: Path,
) -> None:
    vault, _object_id = _vault(tmp_path)
    fixture = ROOT / "tests/fixtures/v2/valid/public-idea-note.md"
    shutil.copyfile(fixture, vault.path("notes") / "ideas" / fixture.name)
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    projection.build(vault)
    service = QueryService(projection)
    search = service.search(vault, "tools", SearchFilters(), ContextScope.PUBLIC_SAFE, 20)
    assert search["count"] == 1
    hits = cast(list[dict[str, Any]], search["hits"])
    assert hits[0]["public_audit"] == {"eligible": True}
    assert hits[0]["classification"]["role"] == "human"
    assert hits[0]["citations"] == []
    context = service.context(vault, "tools", ContextScope.PUBLIC_SAFE, 20, 12_000)
    groups = cast(dict[str, list[dict[str, Any]]], context["groups"])
    exclusions = cast(list[dict[str, Any]], context["exclusions"])
    assert len(groups["human_notes"]) == 1
    assert {item["code"] for item in exclusions} == {"PUBLIC_VISIBILITY_REQUIRED"}
    assert context["truncated"] is False


@pytest.mark.parametrize("record_status", [RecordStatus.ARCHIVED, RecordStatus.SUPERSEDED])
def test_public_safe_context_reports_non_active_candidates(
    tmp_path: Path, record_status: RecordStatus
) -> None:
    vault, _object_id = _vault(tmp_path)
    fixture = ROOT / "tests/fixtures/v2/valid/public-idea-note.md"
    target = vault.path("notes") / "ideas" / fixture.name
    document = parse_object_document(fixture.read_text(encoding="utf-8"))
    assert isinstance(document.object, Note)
    target.write_text(
        render_object_document(
            replace(document, object=replace(document.object, record_status=record_status))
        ),
        encoding="utf-8",
    )
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    projection.build(vault)
    service = QueryService(projection)

    assert (
        service.search(vault, "Local first", SearchFilters(), ContextScope.TRUSTED_LOCAL, 20)[
            "count"
        ]
        == 0
    )
    explicit = service.search(
        vault,
        "Local first",
        SearchFilters(record_status=record_status.value),
        ContextScope.TRUSTED_LOCAL,
        20,
    )
    assert explicit["count"] == 1
    assert cast(list[dict[str, object]], explicit["hits"])[0]["record_status"] == record_status
    assert (
        service.search(vault, "Local first", SearchFilters(), ContextScope.PUBLIC_SAFE, 20)["count"]
        == 0
    )
    context = service.context(vault, "Local first", ContextScope.PUBLIC_SAFE, 20, 12_000)
    exclusions = cast(list[dict[str, object]], context["exclusions"])
    assert "PUBLIC_ACTIVE_REQUIRED" in {item["code"] for item in exclusions}


def test_public_safe_snippet_requires_approval_and_resolved_rights(tmp_path: Path) -> None:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "snippet-vault",
        (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8"),
    )
    source_fixture = ROOT / "tests/fixtures/v2/valid/oss-source.md"
    snippet_fixture = ROOT / "tests/fixtures/v2/valid/snippet.md"
    source_document = parse_object_document(source_fixture.read_text(encoding="utf-8"))
    snippet_document = parse_object_document(snippet_fixture.read_text(encoding="utf-8"))
    assert isinstance(source_document.object, Source)
    assert isinstance(snippet_document.object, Snippet)
    source_target = vault.path("sources") / "oss" / source_fixture.name
    snippet_target = vault.path("snippets") / snippet_fixture.name
    source_target.write_text(
        render_object_document(
            replace(
                source_document,
                object=replace(source_document.object, visibility=Visibility.PUBLIC),
            )
        ),
        encoding="utf-8",
    )
    snippet_target.write_text(
        render_object_document(
            replace(
                snippet_document,
                object=replace(
                    snippet_document.object,
                    visibility=Visibility.PUBLIC,
                    publication_approved=True,
                ),
            )
        ),
        encoding="utf-8",
    )
    projection = SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )
    projection.build(vault)
    service = QueryService(projection)
    assert (
        service.search(vault, "Core", SearchFilters(kind="snippet"), ContextScope.PUBLIC_SAFE, 20)[
            "count"
        ]
        == 1
    )

    source_document = parse_object_document(source_target.read_text(encoding="utf-8"))
    assert isinstance(source_document.object, Source)
    source_target.write_text(
        render_object_document(
            replace(source_document, object=replace(source_document.object, license="NOASSERTION"))
        ),
        encoding="utf-8",
    )
    projection.build(vault)
    assert (
        service.search(vault, "Core", SearchFilters(kind="snippet"), ContextScope.PUBLIC_SAFE, 20)[
            "count"
        ]
        == 0
    )
    context = service.context(vault, "Core", ContextScope.PUBLIC_SAFE, 20, 12_000)
    exclusions = cast(list[dict[str, object]], context["exclusions"])
    assert {item["code"] for item in exclusions} == {"PUBLIC_RIGHTS_UNRESOLVED"}


def test_public_safe_context_rejects_uncited_fact_defense_in_depth(tmp_path: Path) -> None:
    vault, _object_id = _vault(tmp_path)
    fixture = ROOT / "tests/fixtures/v2/valid/public-idea-note.md"
    shutil.copyfile(fixture, vault.path("notes") / "ideas" / fixture.name)
    hit = SearchHit(
        segment_id="seg_uncited",
        object_id="note_01JSTAG7N9Q3V5X8Y2Z4A6B8D1",
        kind="note",
        subtype="idea",
        path="notes/ideas/public-idea-note.md",
        title="Public opinion",
        section_id="sec_public_opinion",
        role="fact",
        ordinal=0,
        text="tools",
        score=0.0,
        tags=(),
        visibility="public",
        record_status="active",
        citations=(),
    )

    class FakeBackend:
        def __init__(self, candidate: SearchHit) -> None:
            self._candidate = candidate

        def search(
            self,
            vault: Vault,
            query: str,
            filters: SearchFilters,
            scope: ContextScope,
            limit: int,
        ) -> tuple[SearchHit, ...]:
            return (self._candidate,) if filters.record_status in {None, "active"} else ()

    context = QueryService(FakeBackend(hit)).context(
        vault, "tools", ContextScope.PUBLIC_SAFE, 20, 12_000
    )
    exclusions = cast(list[dict[str, object]], context["exclusions"])
    assert exclusions == [
        {
            "code": "PUBLIC_FACT_CITATION_REQUIRED",
            "object_id": hit.object_id,
            "segment_id": hit.segment_id,
        }
    ]

    paper = ROOT / "tests/fixtures/v2/valid/paper-source.md"
    shutil.copyfile(paper, vault.path("sources") / "papers" / paper.name)
    mismatched = replace(
        hit,
        segment_id="seg_mismatched",
        citations=(
            {
                "source_id": "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0",
                "locator": {
                    "locator_version": 2,
                    "source_type": "book",
                    "isbn": "9781449373320",
                    "page": 4,
                },
            },
        ),
    )
    mismatch_context = QueryService(FakeBackend(mismatched)).context(
        vault, "tools", ContextScope.PUBLIC_SAFE, 20, 12_000
    )
    mismatch_exclusions = cast(list[dict[str, object]], mismatch_context["exclusions"])
    assert mismatch_exclusions[0]["code"] == "PUBLIC_PROVENANCE_INCOHERENT"


def test_context_budget_never_splits_a_segment_and_closes_after_overflow(
    tmp_path: Path,
) -> None:
    vault, object_id = _vault(tmp_path)
    hits = tuple(
        SearchHit(
            segment_id=f"seg_{index}",
            object_id=object_id,
            kind="note",
            subtype="idea",
            path="notes/ideas/idea-note.md",
            title="Idea",
            section_id="sec_core_idea",
            role="human",
            ordinal=index,
            text=text,
            score=float(index),
            tags=("idea",),
            visibility="private",
            record_status="active",
            citations=(),
        )
        for index, text in enumerate(("1234", "5678", "x"))
    )

    class FakeBackend:
        def search(
            self,
            vault: Vault,
            query: str,
            filters: SearchFilters,
            scope: ContextScope,
            limit: int,
        ) -> tuple[SearchHit, ...]:
            return hits

    context = QueryService(FakeBackend()).context(vault, "idea", ContextScope.TRUSTED_LOCAL, 20, 6)
    groups = cast(dict[str, list[dict[str, object]]], context["groups"])
    exclusions = cast(list[dict[str, object]], context["exclusions"])
    assert [item["snippet"] for item in groups["human_notes"]] == ["1234"]
    assert context["character_count"] == 4
    assert [item["code"] for item in exclusions] == [
        "CHARACTER_BUDGET_EXCEEDED",
        "CHARACTER_BUDGET_EXCEEDED",
    ]
    assert context["truncated"] is True
