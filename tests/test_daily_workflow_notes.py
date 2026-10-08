from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_phase1_notes_cli import SOURCE_ID, _template, _vault
from test_phase5_contracts import validator
from typer.testing import CliRunner

import knowlume.cli as cli
from knowlume.adapters.contract_v2 import parse_object_document
from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.notes import NoteService
from knowlume.domain.values import DomainError

ROOT = Path(__file__).resolve().parents[1]
RUNNER = CliRunner()


def test_note_create_result_contract() -> None:
    fixtures = ROOT / "tests/fixtures/interfaces"
    check = validator("note-create-result-v1.schema.json")
    check.validate(json.loads((fixtures / "valid-note-create-result.json").read_text()))
    for data in json.loads((fixtures / "invalid-note-create-results.json").read_text()):
        assert list(check.iter_errors(data))


@pytest.mark.parametrize("kind", ["idea", "literature", "concept", "synthesis"])
@pytest.mark.parametrize("title", [None, " 中文研究 ", '阅读："引号"'])
def test_titled_creation_json_points_to_actual_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, title: str | None
) -> None:
    vault = _vault(tmp_path)
    monkeypatch.setattr(cli, "read_asset_text", _template)
    args = ["--vault", str(vault.root), "note", "new", "--type", kind, "--json"]
    if kind == "literature":
        args += ["--source", SOURCE_ID]
    if title is not None:
        args += ["--title", title]
    result = RUNNER.invoke(cli.app, args)
    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)
    assert result.stderr == ""
    envelope = json.loads(result.stdout)
    validator("cli-envelope-v1.schema.json").validate(envelope)
    validator("note-create-result-v1.schema.json").validate(envelope["data"])
    assert envelope["command"] == "note new" and envelope["success"] is True
    data = envelope["data"]
    document = parse_object_document((vault.root / data["path"]).read_text(encoding="utf-8"))
    assert str(document.object.id) == data["object_id"]
    assert document.object.title == (title.strip() if title is not None else f"Untitled {kind}")


@pytest.mark.parametrize(
    "title", ["", "  ", "private\nbody", "private\rbody", "a\x00b", "a\tb", "a\x7fb", "a\u2028b"]
)
def test_invalid_title_precedes_scan_and_has_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, title: str
) -> None:
    vault = _vault(tmp_path)
    before = {
        p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*") if p.is_file()
    }
    monkeypatch.setattr(cli, "read_asset_text", _template)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid title reached scanning or mutation")

    monkeypatch.setattr(NoteService, "_healthy_scan", forbidden)
    result = RUNNER.invoke(
        cli.app,
        ["--vault", str(vault.root), "note", "new", "--type", "idea", "--title", title, "--json"],
    )
    assert result.exit_code == 2, (result.stdout, result.stderr, result.exception)
    data = json.loads(result.stdout)
    assert data["command"] == "note new" and data["errors"] == [
        {
            "code": "NOTE_TITLE_INVALID",
            "message": "title must be non-empty and contain no line breaks or control characters",
        }
    ]
    assert result.stderr == "" and "private" not in result.stdout
    assert before == {
        p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*") if p.is_file()
    }


def test_service_creation_result_and_legacy_id_share_implementation(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    service = NoteService(filesystem=FilesystemVault(environment={}), template_reader=_template)
    result = service.create_with_result(vault, "idea", title="Demo")
    assert (vault.root / result.path).is_file()
    assert str(result.object_id) in result.path
    assert str(service.create(vault, "concept")).startswith("note_")
    with pytest.raises(DomainError, match="title"):
        service.create(vault, "idea", title="\n")


def test_custom_notes_path_and_human_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from knowlume.adapters.filesystem import load_vault

    vault = _vault(tmp_path)
    config = vault.root / "knowlume.toml"
    config.write_text(
        config.read_text().replace('notes = "notes"', 'notes = "research/notes"'), encoding="utf-8"
    )
    for folder in ("ideas", "literature", "concepts", "syntheses"):
        (vault.root / "research/notes" / folder).mkdir(parents=True)
    vault = load_vault(vault.root)
    monkeypatch.setattr(cli, "read_asset_text", _template)
    args = ["--vault", str(vault.root), "note", "new", "--type", "idea"]
    created = RUNNER.invoke(cli.app, [*args, "--json", "--title", "Path demo"])
    assert created.exit_code == 0, (created.stdout, created.stderr, created.exception)
    data = json.loads(created.stdout)["data"]
    assert data["path"] == f"research/notes/ideas/{data['object_id']}.md"
    assert (vault.root / data["path"]).is_file()
    human = RUNNER.invoke(cli.app, args)
    assert human.exit_code == 0 and human.stdout.strip().startswith("note_")
    assert len(human.stdout.splitlines()) == 1


@pytest.mark.parametrize(
    "code,exit_code",
    [
        ("NOTE_SOURCE_REQUIRED", 3),
        ("NOTE_SOURCE_INVALID", 3),
        ("VAULT_WRITE_CONFLICT", 4),
        ("VAULT_PATH_UNSAFE", 6),
        ("VAULT_NOT_FOUND", 3),
    ],
)
def test_note_json_business_errors_keep_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, exit_code: int
) -> None:
    vault = _vault(tmp_path)

    def fail(*args: object, **kwargs: object) -> None:
        raise DomainError(code, "safe business diagnostic")

    monkeypatch.setattr(NoteService, "create_with_result", fail)
    result = RUNNER.invoke(
        cli.app, ["--vault", str(vault.root), "note", "new", "--type", "idea", "--json"]
    )
    assert result.exit_code == exit_code and result.stderr == ""
    data = json.loads(result.stdout)
    validator("cli-envelope-v1.schema.json").validate(data)
    assert data["errors"][0]["code"] == code and data["data"] is None


def test_discovery_failure_and_refresh_warning_are_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from knowlume.application.vault import VaultService

    vault = _vault(tmp_path)
    monkeypatch.setattr(cli, "read_asset_text", _template)
    args = ["--vault", str(vault.root), "note", "new", "--type", "idea", "--json"]
    monkeypatch.setattr(cli, "_refresh_warning", lambda _vault: ("INDEX_REFRESH_FAILED",))
    success = RUNNER.invoke(cli.app, args)
    assert success.exit_code == 0 and success.stderr == ""
    assert json.loads(success.stdout)["warnings"] == [
        {"code": "INDEX_REFRESH_FAILED", "message": "Index Refresh Failed"}
    ]

    def fail(*args: object, **kwargs: object) -> None:
        raise DomainError("VAULT_NOT_FOUND", "Vault not found")

    monkeypatch.setattr(VaultService, "discover", fail)
    missing = RUNNER.invoke(cli.app, args)
    assert missing.exit_code == 3 and missing.stderr == ""
    assert json.loads(missing.stdout)["errors"][0]["code"] == "VAULT_NOT_FOUND"


@pytest.mark.parametrize(
    "tail",
    [
        ["--json"],
        ["--type", "--json"],
        ["--type", "idea", "--title", "--json", "--json"],
        ["--type", "idea", "--source", "--", "--title", "--json", "--json"],
    ],
)
def test_note_argument_failures_do_not_discover_vault(
    monkeypatch: pytest.MonkeyPatch, tail: list[str]
) -> None:
    from test_cli_json_arguments import assert_failure

    from knowlume.application.vault import VaultService

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("argument failure reached vault discovery")

    monkeypatch.setattr(VaultService, "discover", forbidden)
    assert_failure(RUNNER.invoke(cli.app, ["note", "new", *tail]), "note new")


def test_explicit_json_title_is_a_value_not_json_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    monkeypatch.setattr(cli, "read_asset_text", _template)
    args = ["--vault", str(vault.root), "note", "new", "--type", "idea", "--title=--json"]
    result = RUNNER.invoke(cli.app, args)
    assert result.exit_code == 0 and result.stdout.strip().startswith("note_")
    for tail in (["--", "--json"], ["--title", "--", "--", "--json"]):
        rejected = RUNNER.invoke(cli.app, ["note", "new", "--type", "idea", *tail])
        assert rejected.exit_code == 2 and rejected.stdout == "" and "Usage:" in rejected.stderr


def test_literature_missing_or_unknown_source_is_failure_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    monkeypatch.setattr(cli, "read_asset_text", _template)
    before = {
        p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*") if p.is_file()
    }
    args = ["--vault", str(vault.root), "note", "new", "--type", "literature", "--json"]
    for tail, code in (
        ([], "NOTE_SOURCE_REQUIRED"),
        (["--source", "src_01JSTAG7N9Q3V5X8Y2Z4A6B8H9"], "NOTE_SOURCE_INVALID"),
    ):
        result = RUNNER.invoke(cli.app, [*args, *tail])
        assert result.exit_code == 3 and result.stderr == ""
        assert json.loads(result.stdout)["errors"][0]["code"] == code
    assert before == {
        p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*") if p.is_file()
    }


def test_literature_retry_id_conflict_preserves_committed_note_and_shard(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    service = NoteService(
        filesystem=FilesystemVault(environment={}),
        template_reader=_template,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8D0",
    )
    service.create_with_result(vault, "literature", source_id_value=SOURCE_ID, title="First")
    before = {
        p.relative_to(vault.root): p.read_bytes()
        for p in vault.root.rglob("*")
        if p.is_file() and not p.is_relative_to(vault.path("state"))
    }
    with pytest.raises(DomainError) as caught:
        service.create_with_result(vault, "literature", source_id_value=SOURCE_ID, title="Retry")
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    assert before == {
        p.relative_to(vault.root): p.read_bytes()
        for p in vault.root.rglob("*")
        if p.is_file() and not p.is_relative_to(vault.path("state"))
    }


def test_real_index_refresh_failure_keeps_creation_success_and_human_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from knowlume.adapters.sqlite_projection import SQLiteProjection

    vault = _vault(tmp_path)
    monkeypatch.setattr(cli, "read_asset_text", _template)

    def failed_refresh(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic-index-failure")

    monkeypatch.setattr(SQLiteProjection, "refresh_if_present", failed_refresh)
    args = ["--vault", str(vault.root), "note", "new", "--type", "idea"]
    result = RUNNER.invoke(cli.app, [*args, "--json"])
    envelope = json.loads(result.stdout)
    assert result.exit_code == 0 and result.stderr == "" and envelope["success"]
    assert envelope["warnings"][0]["code"] == "INDEX_REFRESH_FAILED"
    assert (vault.root / envelope["data"]["path"]).is_file()
    human = RUNNER.invoke(cli.app, args)
    assert human.exit_code == 0 and human.stdout.strip().startswith("note_")
    assert "INDEX_REFRESH_FAILED" in human.stderr
    invalid = RUNNER.invoke(cli.app, [*args, "--title", "secret\nbody"])
    assert invalid.exit_code == 2 and invalid.stdout == ""
    assert "NOTE_TITLE_INVALID" in invalid.stderr and "secret" not in invalid.stderr


def test_invalid_fact_reference_blocks_creation_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    monkeypatch.setattr(cli, "read_asset_text", _template)
    service = NoteService(filesystem=FilesystemVault(environment={}), template_reader=_template)
    existing = service.create_with_result(vault, "idea")
    with (vault.root / existing.path).open("a", encoding="utf-8") as stream:
        stream.write(
            "\n<!-- knowlume:section id=sec_invalid_fact role=fact -->\n## Demo\n\n"
            "<!-- knowlume:fact\ncitations:\n"
            "  - source_id: src_01JSTAG7N9Q3V5X8Y2Z4A6B8H9\n"
            "    locator:\n      locator_version: 2\n      source_type: paper\n"
            "      page: 1\n-->\nSynthetic invalid reference.\n"
        )
    before = {
        p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*") if p.is_file()
    }
    result = RUNNER.invoke(
        cli.app,
        ["--vault", str(vault.root), "note", "new", "--type", "idea", "--json"],
    )
    assert result.exit_code == 3 and result.stderr == ""
    assert json.loads(result.stdout)["errors"][0]["code"] == "VAULT_INVALID"
    assert before == {
        p.relative_to(vault.root): p.read_bytes() for p in vault.root.rglob("*") if p.is_file()
    }
