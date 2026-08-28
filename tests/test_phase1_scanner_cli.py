from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from knowlume.adapters.contract_v2 import parse_object_document
from knowlume.adapters.filesystem import FilesystemVault, load_vault
from knowlume.application.scanning import scan_vault
from knowlume.cli import app
from knowlume.domain.models import Note, Source
from knowlume.ports.vault import Vault

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/v2"
CONFIG_TEXT = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
runner = CliRunner()


def _init(tmp_path: Path) -> Vault:
    root = tmp_path / "vault"
    FilesystemVault(environment={}).initialize(root, CONFIG_TEXT)
    return load_vault(root)


def _destination(vault: Vault, source: Path) -> Path:
    document = parse_object_document(source.read_text(encoding="utf-8"))
    obj = document.object
    if isinstance(obj, Source):
        folder = {"paper": "papers", "web": "web", "book": "books", "oss": "oss"}[
            obj.source_type.value
        ]
        return vault.root / "sources" / folder / source.name
    if isinstance(obj, Note):
        folder = {
            "idea": "ideas",
            "literature": "literature",
            "concept": "concepts",
            "synthesis": "syntheses",
        }[obj.note_type.value]
        return vault.root / "notes" / folder / source.name
    if obj.id.kind.value == "snippet":
        return vault.root / "snippets" / source.name
    return vault.root / "ai/artifacts" / source.name


def _copy_valid_objects(vault: Vault) -> None:
    for source in sorted((FIXTURES / "valid").glob("*.md")):
        shutil.copyfile(source, _destination(vault, source))


def _copy_valid_vault(vault: Vault) -> None:
    _copy_valid_objects(vault)
    for source in sorted((FIXTURES / "valid/relations").glob("*.yaml")):
        shutil.copyfile(source, vault.root / "relations" / source.name)


def _invalid_destination(vault: Vault, source: Path) -> Path:
    if source.name.startswith("paper-"):
        return vault.root / "sources" / "papers" / source.name
    if source.name == "snippet-line-range.md":
        return vault.root / "snippets" / source.name
    if source.name in {"idea-evergreen.md", "idea-mature.md"}:
        return vault.root / "notes/ideas" / source.name
    return vault.root / "notes/concepts" / source.name


def test_scan_is_deterministic_and_healthy_for_all_valid_v2_fixtures(tmp_path: Path) -> None:
    vault = _init(tmp_path)
    _copy_valid_vault(vault)
    first = scan_vault(vault)
    second = scan_vault(vault)
    assert first == second
    assert first.healthy
    assert first.findings == ()
    assert first.object_counts() == {
        "source": 6,
        "note": 5,
        "snippet": 1,
        "ai_artifact": 2,
    }


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("ai-unpromoted.md", "AI_ARTIFACT_UNPROMOTED"),
        ("duplicate-section.md", "SECTION_ID_DUPLICATE"),
        ("fact-missing-citation.md", "NOTE_BLOCK_METADATA_MISSING"),
        ("fact-source-mismatch.md", "FACT_LOCATOR_MISMATCH"),
        ("idea-evergreen.md", "NOTE_MATURITY_INVALID"),
        ("idea-mature.md", "NOTE_MATURITY_INVALID"),
        ("missing-human-section.md", "NOTE_HUMAN_SECTION_MISSING"),
        ("paper-arxiv-version-without-id.md", "FIELD_INVALID"),
        ("paper-attachment-path.md", "FIELD_INVALID"),
        ("snippet-line-range.md", "SNIPPET_RANGE_INVALID"),
        ("unknown-role.md", "FIELD_INVALID"),
    ],
)
def test_scanner_reports_every_invalid_object_fixture(tmp_path: Path, name: str, code: str) -> None:
    vault = _init(tmp_path)
    _copy_valid_objects(vault)
    source = FIXTURES / "invalid" / name
    shutil.copyfile(source, _invalid_destination(vault, source))
    result = scan_vault(vault)
    assert code in {finding.code for finding in result.findings}


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("duplicate-key.yaml", "RELATION_DUPLICATE"),
        ("noncanonical-related.yaml", "RELATION_NOT_CANONICAL"),
        ("public-private.yaml", "RELATION_PRIVATE_DEPENDENCY"),
        ("shard-owner-mismatch.yaml", "RELATION_SHARD_OWNER_MISMATCH"),
        ("wrong-kind.yaml", "RELATION_KIND_INVALID"),
    ],
)
def test_scanner_reports_every_invalid_relation_fixture(
    tmp_path: Path, name: str, code: str
) -> None:
    vault = _init(tmp_path)
    _copy_valid_objects(vault)
    source = FIXTURES / "invalid/relations" / name
    shutil.copyfile(source, vault.root / "relations" / name)
    result = scan_vault(vault)
    assert code in {finding.code for finding in result.findings}


def test_scanner_reports_cardinality_duplicate_identity_and_layout(tmp_path: Path) -> None:
    vault = _init(tmp_path)
    _copy_valid_objects(vault)
    for source in sorted((FIXTURES / "invalid/cardinality").rglob("*.yaml")):
        shutil.copyfile(source, vault.root / "relations" / source.name)
    duplicate = FIXTURES / "valid/idea-note.md"
    shutil.copyfile(duplicate, vault.root / "notes/ideas/duplicate.md")
    misplaced = FIXTURES / "valid/public-idea-note.md"
    misplaced_text = misplaced.read_text(encoding="utf-8").replace(
        "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D1",
        "note_01JSTAG7N9Q3V5X8Y2Z4A6B8H9",
    )
    (vault.root / "sources/papers/misplaced.md").write_text(misplaced_text, encoding="utf-8")
    codes = {finding.code for finding in scan_vault(vault).findings}
    assert {
        "LITERATURE_SUMMARY_MISSING",
        "SYNTHESIS_TARGETS_INSUFFICIENT",
        "OBJECT_ID_DUPLICATE",
        "OBJECT_LAYOUT_INVALID",
    } <= codes


def test_scan_status_and_lint_commands_share_scanner_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _init(tmp_path)
    _copy_valid_vault(vault)
    scan = runner.invoke(app, ["--vault", str(vault.root), "scan"])
    assert scan.exit_code == 0
    assert "14 objects" in scan.stdout
    status = runner.invoke(app, ["--vault", str(vault.root), "status"])
    assert status.exit_code == 0
    assert "Vault is healthy" in status.stdout
    lint = runner.invoke(app, ["--vault", str(vault.root), "lint"])
    assert lint.exit_code == 0
    assert "0 finding(s)" in lint.stdout

    invalid = FIXTURES / "invalid/idea-mature.md"
    destination = _invalid_destination(vault, invalid)
    shutil.copyfile(invalid, destination)
    lint = runner.invoke(app, ["--vault", str(vault.root), "lint"])
    assert lint.exit_code == 3
    assert "NOTE_MATURITY_INVALID" in lint.stdout
    monkeypatch.setattr(
        "knowlume.cli.changed_paths",
        lambda _: {destination.relative_to(vault.root).as_posix()},
    )
    changed = runner.invoke(app, ["--vault", str(vault.root), "lint", "--changed"])
    assert changed.exit_code == 3
    assert "NOTE_MATURITY_INVALID" in changed.stdout
    conflict = runner.invoke(app, ["--vault", str(vault.root), "lint", "--strict", "--changed"])
    assert conflict.exit_code == 2
