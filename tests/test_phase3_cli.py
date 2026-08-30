from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import knowlume.cli as cli
from knowlume.adapters.filesystem import FilesystemVault
from knowlume.adapters.sqlite_projection import SQLiteProjection

ROOT = Path(__file__).resolve().parents[1]
RUNNER = CliRunner()


def _vault(tmp_path: Path) -> tuple[Path, str]:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "vault",
        (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8"),
    )
    fixture = ROOT / "tests/fixtures/v2/valid/idea-note.md"
    shutil.copyfile(fixture, vault.path("notes") / "ideas" / fixture.name)
    return vault.root, "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"


def _projection() -> SQLiteProjection:
    return SQLiteProjection(
        ddl_reader=lambda _name: (ROOT / "schemas/v2/sqlite-projection-v2.sql").read_text(
            encoding="utf-8"
        )
    )


def test_phase3_cli_index_grep_get_search_and_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, object_id = _vault(tmp_path)
    projection = _projection()
    monkeypatch.setattr(cli, "_projection", lambda: projection)
    prefix = ["--vault", str(root)]

    status = RUNNER.invoke(cli.app, [*prefix, "index", "status", "--json"])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["data"]["state"] == "missing"

    grep = RUNNER.invoke(cli.app, [*prefix, "grep", "Knowledge", "--json"])
    get = RUNNER.invoke(cli.app, [*prefix, "get", object_id, "--json"])
    assert grep.exit_code == get.exit_code == 0
    assert json.loads(grep.stdout)["data"]["count"] == 1
    assert json.loads(get.stdout)["data"]["object_id"] == object_id

    missing_search = RUNNER.invoke(cli.app, [*prefix, "search", "Knowledge", "--json"])
    assert missing_search.exit_code == 5
    assert json.loads(missing_search.stdout)["errors"][0]["code"] == "INDEX_NOT_FOUND"

    idea_path = root / "notes" / "ideas" / "idea-note.md"
    idea_path.write_text(
        idea_path.read_text(encoding="utf-8").replace("Knowledge tools", "Knowledge 知识 tools"),
        encoding="utf-8",
    )

    build = RUNNER.invoke(cli.app, [*prefix, "index", "build", "--json"])
    search = RUNNER.invoke(cli.app, [*prefix, "search", "Knowledge", "--json"])
    bilingual = RUNNER.invoke(cli.app, [*prefix, "search", "Knowledge 知识", "--json"])
    filtered = RUNNER.invoke(
        cli.app,
        [
            *prefix,
            "search",
            "Knowledge",
            "--kind",
            "note",
            "--subtype",
            "idea",
            "--visibility",
            "private",
            "--record-status",
            "active",
            "--maturity",
            "seed",
            "--tag",
            "idea",
            "--role",
            "human",
            "--limit",
            "1",
            "--json",
        ],
    )
    tag_and = RUNNER.invoke(
        cli.app,
        [
            *prefix,
            "search",
            "Knowledge",
            "--tag",
            "idea",
            "--tag",
            "missing",
            "--json",
        ],
    )
    workflow_filter = RUNNER.invoke(
        cli.app,
        [*prefix, "search", "Knowledge", "--workflow-stage", "reading", "--json"],
    )
    review_filter = RUNNER.invoke(
        cli.app,
        [*prefix, "search", "Knowledge", "--review-status", "promoted", "--json"],
    )
    context = RUNNER.invoke(
        cli.app,
        [*prefix, "context", "Knowledge", "--scope", "trusted-local", "--json"],
    )
    assert (
        build.exit_code
        == search.exit_code
        == bilingual.exit_code
        == filtered.exit_code
        == tag_and.exit_code
        == workflow_filter.exit_code
        == review_filter.exit_code
        == context.exit_code
        == 0
    )
    assert json.loads(build.stdout)["data"]["state"] == "fresh"
    assert json.loads(search.stdout)["data"]["hits"][0]["object_id"] == object_id
    assert json.loads(bilingual.stdout)["data"]["count"] == 1
    assert json.loads(filtered.stdout)["data"]["count"] == 1
    assert json.loads(tag_and.stdout)["data"]["count"] == 0
    assert json.loads(workflow_filter.stdout)["data"]["count"] == 0
    assert json.loads(review_filter.stdout)["data"]["count"] == 0
    assert json.loads(context.stdout)["data"]["groups"]["human_notes"]


def test_context_scope_is_required_and_rebuild_repairs_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _object_id = _vault(tmp_path)
    projection = _projection()
    monkeypatch.setattr(cli, "_projection", lambda: projection)
    prefix = ["--vault", str(root)]
    missing_scope = RUNNER.invoke(cli.app, [*prefix, "context", "Knowledge"])
    assert missing_scope.exit_code == 2

    database = root / ".knowlume" / "kb.sqlite"
    database.write_bytes(b"not sqlite")
    status = RUNNER.invoke(cli.app, [*prefix, "index", "status", "--json"])
    assert json.loads(status.stdout)["data"]["state"] == "corrupt"
    corrupt_bytes = database.read_bytes()
    search = RUNNER.invoke(cli.app, [*prefix, "search", "Knowledge", "--json"])
    assert search.exit_code == 3
    assert json.loads(search.stdout)["errors"][0]["code"] == "INDEX_CORRUPT"
    assert database.read_bytes() == corrupt_bytes
    grep = RUNNER.invoke(cli.app, [*prefix, "grep", "Knowledge", "--json"])
    get = RUNNER.invoke(
        cli.app,
        [*prefix, "get", "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0", "--json"],
    )
    assert grep.exit_code == get.exit_code == 0
    assert json.loads(grep.stdout)["data"]["count"] == 1
    assert json.loads(get.stdout)["data"]["object_id"] == "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
    rebuild = RUNNER.invoke(cli.app, [*prefix, "index", "rebuild", "--json"])
    assert rebuild.exit_code == 0
    assert json.loads(rebuild.stdout)["data"]["state"] == "fresh"


def test_phase3_cli_typed_grep_and_get_input_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _object_id = _vault(tmp_path)
    monkeypatch.setattr(cli, "_projection", _projection)
    prefix = ["--vault", str(root)]

    invalid_query = RUNNER.invoke(cli.app, [*prefix, "grep", "--json", "--", "---"])
    missing_object = RUNNER.invoke(
        cli.app,
        [*prefix, "get", "note_01JSTAG7N9Q3V5X8Y2Z4A6B8ZZ", "--json"],
    )

    assert invalid_query.exit_code == 2
    assert json.loads(invalid_query.stdout)["errors"][0]["code"] == "SEARCH_QUERY_INVALID"
    assert missing_object.exit_code == 3
    assert json.loads(missing_object.stdout)["errors"][0]["code"] == "OBJECT_NOT_FOUND"


def test_cli_mutation_survives_refresh_failure_and_leaves_index_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "vault",
        (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8"),
    )
    fixture = ROOT / "tests/fixtures/v2/valid/phase2a-paper-source.md"
    target = vault.path("sources") / "papers" / fixture.name
    shutil.copyfile(fixture, target)
    projection = _projection()
    projection.build(vault)

    class BrokenRefresh:
        def refresh_if_present(self, _vault: object) -> bool:
            raise RuntimeError("injected refresh failure")

    monkeypatch.setattr(cli, "_projection", BrokenRefresh)
    result = RUNNER.invoke(
        cli.app,
        [
            "--vault",
            str(vault.root),
            "process",
            "src_01JSTAG7N9Q3V5X8Y2Z4A6B8E0",
            "--to",
            "reading",
            "--json",
        ],
    )

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload["data"]["current_stage"] == "reading"
    assert payload["warnings"] == [
        {
            "code": "INDEX_REFRESH_FAILED",
            "message": "Index Refresh Failed",
        }
    ]
    assert "workflow_stage: reading" in target.read_text(encoding="utf-8")
    assert projection.status(vault)["state"] == "stale"
