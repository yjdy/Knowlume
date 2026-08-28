from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from knowlume.adapters.contract_v2 import parse_object_document
from knowlume.adapters.filesystem import FilesystemVault, load_vault
from knowlume.application.notes import NoteService
from knowlume.application.scanning import scan_vault
from knowlume.cli import app
from knowlume.domain.models import Note, NoteBody
from knowlume.domain.values import DomainError, NoteType
from knowlume.ports.vault import Vault

ROOT = Path(__file__).resolve().parents[1]
CONFIG_TEXT = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
SOURCE_FIXTURE = ROOT / "tests/fixtures/v2/valid/paper-source.md"
SOURCE_ID = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0"
runner = CliRunner()


def _template(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _vault(tmp_path: Path) -> Vault:
    root = tmp_path / "vault"
    FilesystemVault(environment={}).initialize(root, CONFIG_TEXT)
    shutil.copyfile(SOURCE_FIXTURE, root / "sources/papers/paper.md")
    return load_vault(root)


def _ids() -> Iterator[str]:
    yield from (
        "01JSTAG7N9Q3V5X8Y2Z4A6B8D0",
        "01JSTAG7N9Q3V5X8Y2Z4A6B8D1",
        "01JSTAG7N9Q3V5X8Y2Z4A6B8D2",
        "01JSTAG7N9Q3V5X8Y2Z4A6B8D3",
    )


def test_every_note_type_can_be_created_and_scanned(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    identifiers = _ids()
    service = NoteService(
        filesystem=FilesystemVault(environment={}),
        template_reader=_template,
        clock=lambda: datetime(2026, 8, 27, 8, 0, tzinfo=UTC),
        ulid_factory=lambda: next(identifiers),
    )
    created = {
        NoteType.IDEA: service.create(vault, "idea"),
        NoteType.LITERATURE: service.create(vault, "literature", source_id_value=SOURCE_ID),
        NoteType.CONCEPT: service.create(vault, "concept"),
        NoteType.SYNTHESIS: service.create(vault, "synthesis"),
    }
    result = scan_vault(vault)
    assert result.healthy
    for note_type, object_id in created.items():
        scanned = result.objects[object_id]
        assert isinstance(scanned.document.object, Note)
        assert scanned.document.object.note_type is note_type
        assert scanned.document.object.visibility.value == "private"
        assert isinstance(scanned.document.body, NoteBody)
        assert any(section.role.value == "human" for section in scanned.document.body.sections)
    literature_id = created[NoteType.LITERATURE]
    assert result.relation_shards[literature_id].shard.relations[0].to_id.value == SOURCE_ID


def test_literature_requires_an_explicit_existing_source(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    service = NoteService(filesystem=FilesystemVault(environment={}), template_reader=_template)
    with pytest.raises(DomainError) as missing:
        service.create(vault, "literature")
    assert missing.value.code == "NOTE_SOURCE_REQUIRED"
    with pytest.raises(DomainError) as unknown:
        service.create(
            vault,
            "literature",
            source_id_value="src_01JSTAG7N9Q3V5X8Y2Z4A6B8H9",
        )
    assert unknown.value.code == "NOTE_SOURCE_INVALID"
    assert list((vault.root / "notes/literature").iterdir()) == []


def test_note_show_and_evolve_preserve_identity_sections_and_body(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    service = NoteService(
        filesystem=FilesystemVault(environment={}),
        template_reader=_template,
        clock=lambda: datetime(2026, 8, 27, 8, 0, tzinfo=UTC),
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8D0",
    )
    object_id = service.create(vault, "idea")
    before = parse_object_document(service.show(vault, str(object_id)))
    evolved_id = service.evolve(vault, str(object_id), "concept")
    after = parse_object_document(service.show(vault, str(object_id)))
    assert evolved_id == object_id
    assert before.object.id == after.object.id
    assert isinstance(before.body, NoteBody) and isinstance(after.body, NoteBody)
    assert before.body.sections == after.body.sections
    assert isinstance(after.object, Note)
    assert after.object.note_type is NoteType.CONCEPT
    assert len(after.object.type_history) == 1
    assert after.object.type_history[0].actor.id == "cli-user"
    assert scan_vault(vault).healthy


class ConflictFilesystem(FilesystemVault):
    def atomic_write(
        self,
        vault: Vault,
        relative_path: str,
        content: bytes,
        expected_checksum: str | None,
    ) -> str:
        (vault.root / relative_path).write_text("newer external content", encoding="utf-8")
        return super().atomic_write(vault, relative_path, content, expected_checksum)


def test_evolution_conflict_preserves_newer_content(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    creator = NoteService(
        filesystem=FilesystemVault(environment={}),
        template_reader=_template,
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8D0",
    )
    object_id = creator.create(vault, "idea")
    service = NoteService(filesystem=ConflictFilesystem(), template_reader=_template)
    with pytest.raises(DomainError) as caught:
        service.evolve(vault, str(object_id), "concept")
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    path = vault.root / f"notes/ideas/{object_id}.md"
    assert path.read_text(encoding="utf-8") == "newer external content"


def test_note_cli_create_show_evolve_and_invalid_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    monkeypatch.setattr("knowlume.cli.read_asset_text", _template)
    created = runner.invoke(app, ["--vault", str(vault.root), "note", "new", "--type", "idea"])
    assert created.exit_code == 0
    object_id = created.stdout.strip()
    shown = runner.invoke(app, ["--vault", str(vault.root), "note", "show", object_id])
    assert shown.exit_code == 0
    assert f"id: {object_id}" in shown.stdout
    evolved = runner.invoke(
        app,
        ["--vault", str(vault.root), "note", "evolve", object_id, "--to", "concept"],
    )
    assert evolved.exit_code == 0
    repeated = runner.invoke(
        app,
        ["--vault", str(vault.root), "note", "evolve", object_id, "--to", "concept"],
    )
    assert repeated.exit_code == 3
    assert "NOTE_TRANSITION_INVALID" in repeated.stderr
