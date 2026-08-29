from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from click import unstyle
from test_phase2b_capture import Repositories, Zotero, _item
from typer.testing import CliRunner

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.capture import AddResult, UnifiedCaptureService
from knowlume.cli import app
from knowlume.domain.values import DomainError, ObjectId

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")


@dataclass
class Service:
    error: DomainError | None = None
    warnings: tuple[str, ...] = ()

    def add(self, *args: object, **kwargs: object) -> AddResult:
        if self.error:
            raise self.error
        return AddResult(
            "https://github.com/openai/openai-python",
            None,
            "repo",
            "oss",
            "repo:github.com/openai/openai-python@" + "a" * 40,
            ObjectId("src_01JSTAG7N9Q3V5X8Y2Z4A6B8C3"),
            True,
            self.warnings,
        )


def test_add_json_and_human_results_use_one_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("knowlume.cli._resolved_vault", lambda ctx: object())
    monkeypatch.setattr("knowlume.cli._capture_service", lambda: Service())
    base = ["--vault", str(tmp_path), "add", "https://github.com/openai/openai-python"]
    machine = runner.invoke(app, [*base, "--json"])
    assert machine.exit_code == 0
    document = json.loads(machine.stdout)
    assert document["command"] == "add"
    golden = json.loads(
        (ROOT / "tests/fixtures/interfaces/valid-add-result-created.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["data"] == golden == Service().add().data()
    human = runner.invoke(app, base)
    assert human.exit_code == 0
    assert "Created repo Source src_" in human.stdout


def test_add_warning_envelope_and_human_streams_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("knowlume.cli._resolved_vault", lambda ctx: object())
    monkeypatch.setattr(
        "knowlume.cli._capture_service",
        lambda: Service(warnings=("PAPER_ATTACHMENT_UNAVAILABLE",)),
    )
    base = ["--vault", str(tmp_path), "add", "https://github.com/openai/openai-python"]
    machine = runner.invoke(app, [*base, "--json"])
    assert machine.exit_code == 0 and machine.stderr == ""
    assert json.loads(machine.stdout)["warnings"] == [
        {
            "code": "PAPER_ATTACHMENT_UNAVAILABLE",
            "message": "Paper Attachment Unavailable",
        }
    ]
    human = runner.invoke(app, base)
    assert human.exit_code == 0
    assert "Created repo Source" in human.stdout
    assert human.stderr == "WARNING PAPER_ATTACHMENT_UNAVAILABLE\n"


@pytest.mark.parametrize(
    ("code", "exit_code"),
    [
        ("ADD_INPUT_INVALID", 2),
        ("ADD_TYPE_AMBIGUOUS", 3),
        ("ADD_IDENTITY_CONFLICT", 3),
        ("ADD_WRITE_CONFLICT", 4),
        ("ADD_METADATA_UNAVAILABLE", 5),
    ],
)
def test_add_stable_errors_match_in_human_and_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    exit_code: int,
) -> None:
    monkeypatch.setattr("knowlume.cli._resolved_vault", lambda ctx: object())
    monkeypatch.setattr("knowlume.cli._capture_service", lambda: Service(DomainError(code, "safe")))
    base = ["--vault", str(tmp_path), "add", "input"]
    human = runner.invoke(app, base)
    assert human.exit_code == exit_code and code in human.stderr
    machine = runner.invoke(app, [*base, "--json"])
    assert machine.exit_code == exit_code
    document = json.loads(machine.stdout)
    assert document["errors"] == [{"code": code, "message": "safe"}]


def test_add_help_is_public_and_snippet_group_is_absent() -> None:
    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0 and "add" in root.stdout
    add = runner.invoke(app, ["add", "--help"])
    assert add.exit_code == 0
    help_text = unstyle(add.stdout)
    assert "--type" in help_text and "--json" in help_text
    assert runner.invoke(app, ["snippet", "--help"]).exit_code == 2


@pytest.mark.parametrize(
    ("value", "requested", "expected"),
    [
        ("arXiv:2401.12345", None, "paper"),
        ("0-306-40615-2", None, "book"),
        ("https://example.test/page", None, "web"),
        ("https://github.com/acme/project", None, "repo"),
        ("10.1000/paper", "paper", "paper"),
        ("arXiv:2401.12345", "paper", "paper"),
        ("10.1000/book", "book", "book"),
        ("0-306-40615-2", "book", "book"),
        ("https://example.test/page", "web", "web"),
        ("https://code.example.test/team/project", "repo", "repo"),
    ],
)
def test_all_capture_paths_and_valid_overrides_have_command_level_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    requested: str | None,
    expected: str,
) -> None:
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    web_url = "https://example.test/page"
    paper = _item(
        "journalArticle",
        key="PAPER001",
        doi="10.1000/paper",
        arxiv="2401.12345",
    )
    book = _item(
        "book",
        key="BOOK0001",
        doi="10.1000/book",
        isbn="9780306406157",
    )
    capture = UnifiedCaptureService(
        filesystem=filesystem,
        zotero=Zotero(
            {
                ("doi", "10.1000/paper"): (paper,),
                ("arxiv", "2401.12345"): (paper,),
                ("doi", "10.1000/book"): (book,),
                ("isbn", "9780306406157"): (book,),
                ("url", web_url): (_item("webpage", key="WEBP0001", url=web_url),),
            }
        ),
        repositories=Repositories(),
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
    )
    monkeypatch.setattr("knowlume.cli._capture_service", lambda: capture)
    arguments = ["--vault", str(vault.root), "add", value]
    if requested:
        arguments.extend(("--type", requested))
    result = runner.invoke(app, [*arguments, "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["requested_type"] == requested
    assert data["detected_type"] == expected
    assert data["source_type"] == ("oss" if expected == "repo" else expected)


def test_cli_repository_duplicate_and_changed_head_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    repositories = Repositories()
    ids = iter(
        (
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G1",
            "01JSTAG7N9Q3V5X8Y2Z4A6B8G2",
        )
    )
    capture = UnifiedCaptureService(
        filesystem=filesystem,
        zotero=Zotero({}),
        repositories=repositories,
        ulid_factory=lambda: next(ids),
    )
    monkeypatch.setattr("knowlume.cli._capture_service", lambda: capture)
    base = [
        "--vault",
        str(vault.root),
        "add",
        "https://github.com/acme/project",
        "--json",
    ]
    first = json.loads(runner.invoke(app, base).stdout)["data"]
    duplicate = json.loads(runner.invoke(app, base).stdout)["data"]
    assert duplicate["source_id"] == first["source_id"]
    assert duplicate["created"] is False
    repositories.commit = "b" * 40
    changed = json.loads(runner.invoke(app, base).stdout)["data"]
    assert changed["source_id"] != first["source_id"]
    assert changed["created"] is True
