from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from knowlume.adapters.contract_v2 import parse_object_document, parse_relation_shard
from knowlume.adapters.filesystem import FilesystemVault, load_vault
from knowlume.application.relations import RelationService
from knowlume.application.scanning import scan_vault
from knowlume.cli import app
from knowlume.domain.models import Note, Source
from knowlume.domain.values import DomainError
from knowlume.ports.vault import Vault

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/v2/valid"
CONFIG_TEXT = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
IDEA_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
PUBLIC_IDEA_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D1"
LITERATURE_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D2"
PAPER_ID = "src_01JSTAG7N9Q3V5X8Y2Z4A6B8C0"
PUBLIC_SECTION_ID = "sec_public_opinion"
runner = CliRunner()


def _vault(tmp_path: Path) -> Vault:
    root = tmp_path / "vault"
    FilesystemVault(environment={}).initialize(root, CONFIG_TEXT)
    for source in sorted(FIXTURES.glob("*.md")):
        document = parse_object_document(source.read_text(encoding="utf-8"))
        obj = document.object
        if isinstance(obj, Source):
            folder = {"paper": "papers", "web": "web", "book": "books", "oss": "oss"}[
                obj.source_type.value
            ]
            destination = root / "sources" / folder / source.name
        elif isinstance(obj, Note):
            folder = {
                "idea": "ideas",
                "literature": "literature",
                "concept": "concepts",
                "synthesis": "syntheses",
            }[obj.note_type.value]
            destination = root / "notes" / folder / source.name
        elif obj.id.kind.value == "snippet":
            destination = root / "snippets" / source.name
        else:
            destination = root / "ai/artifacts" / source.name
        shutil.copyfile(source, destination)
    return load_vault(root)


def _service(filesystem: FilesystemVault | None = None) -> RelationService:
    return RelationService(
        filesystem=filesystem or FilesystemVault(environment={}),
        clock=lambda: datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
    )


def test_related_to_is_stored_once_canonically_and_inverse_is_derived(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    service = _service()
    added = service.add(vault, PUBLIC_IDEA_ID, IDEA_ID, "related_to")
    assert str(added.from_id) == IDEA_ID
    assert str(added.to_id) == PUBLIC_IDEA_ID
    shard_path = vault.root / f"relations/{IDEA_ID}.yaml"
    shard = parse_relation_shard(shard_path.read_text(encoding="utf-8"))
    assert len(shard.relations) == 1
    assert shard.relations[0].actor.id == "cli-user"
    assert shard.relations[0].created_at == datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    assert not (vault.root / f"relations/{PUBLIC_IDEA_ID}.yaml").exists()
    assert [item.direction for item in service.list(vault, PUBLIC_IDEA_ID)] == ["incoming"]


def test_stable_section_duplicate_and_exact_remove(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    service = _service()
    service.add(
        vault,
        IDEA_ID,
        PUBLIC_IDEA_ID,
        "related_to",
        to_section_value=PUBLIC_SECTION_ID,
    )
    service.add(vault, IDEA_ID, PUBLIC_IDEA_ID, "related_to")
    before = (vault.root / f"relations/{IDEA_ID}.yaml").read_bytes()
    with pytest.raises(DomainError) as duplicate:
        service.add(vault, IDEA_ID, PUBLIC_IDEA_ID, "related_to")
    assert duplicate.value.code == "RELATION_ALREADY_EXISTS"
    assert (vault.root / f"relations/{IDEA_ID}.yaml").read_bytes() == before
    service.remove(vault, IDEA_ID, PUBLIC_IDEA_ID, "related_to")
    remaining = parse_relation_shard(
        (vault.root / f"relations/{IDEA_ID}.yaml").read_text(encoding="utf-8")
    ).relations
    assert len(remaining) == 1
    assert str(remaining[0].to_section_id) == PUBLIC_SECTION_ID


@pytest.mark.parametrize(
    ("from_id", "to_id", "relation_type", "section", "code"),
    [
        (PAPER_ID, IDEA_ID, "cites", None, "RELATION_KIND_INVALID"),
        (IDEA_ID, PAPER_ID, "cites", "sec_missing", "RELATION_SECTION_MISSING"),
        (PUBLIC_IDEA_ID, IDEA_ID, "supports", None, "RELATION_PRIVATE_DEPENDENCY"),
        (
            IDEA_ID,
            "note_01JSTAG7N9Q3V5X8Y2Z4A6B8H9",
            "related_to",
            None,
            "RELATION_ENDPOINT_MISSING",
        ),
    ],
)
def test_invalid_relation_adds_do_not_write(
    tmp_path: Path,
    from_id: str,
    to_id: str,
    relation_type: str,
    section: str | None,
    code: str,
) -> None:
    vault = _vault(tmp_path)
    with pytest.raises(DomainError) as caught:
        _service().add(
            vault,
            from_id,
            to_id,
            relation_type,
            to_section_value=section,
        )
    assert caught.value.code == code
    assert list((vault.root / "relations").iterdir()) == []


class ConflictFilesystem(FilesystemVault):
    def atomic_write(
        self,
        vault: Vault,
        relative_path: str,
        content: bytes,
        expected_checksum: str | None,
    ) -> str:
        (vault.root / relative_path).write_text("external edit", encoding="utf-8")
        return super().atomic_write(vault, relative_path, content, expected_checksum)


def test_conflict_preserves_external_relation_content(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    with pytest.raises(DomainError) as caught:
        _service(ConflictFilesystem(environment={})).add(
            vault, IDEA_ID, PUBLIC_IDEA_ID, "related_to"
        )
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    assert (vault.root / f"relations/{IDEA_ID}.yaml").read_text(encoding="utf-8") == "external edit"


def test_relation_cardinality_is_recomputed_after_remove(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    service = _service()
    service.add(vault, LITERATURE_ID, PAPER_ID, "summarizes")
    assert "LITERATURE_SUMMARY_MISSING" not in {
        finding.code for finding in scan_vault(vault).findings
    }
    service.remove(vault, LITERATURE_ID, PAPER_ID, "summarizes")
    assert "LITERATURE_SUMMARY_MISSING" in {finding.code for finding in scan_vault(vault).findings}


def test_relation_cli_add_list_remove(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    base = ["--vault", str(vault.root), "relation"]
    added = runner.invoke(
        app,
        [*base, "add", PUBLIC_IDEA_ID, IDEA_ID, "--type", "related_to"],
    )
    assert added.exit_code == 0
    assert f"{IDEA_ID} -> {PUBLIC_IDEA_ID}" in added.stdout
    listed = runner.invoke(app, [*base, "list", PUBLIC_IDEA_ID])
    assert listed.exit_code == 0
    assert "incoming related_to" in listed.stdout
    removed = runner.invoke(
        app,
        [*base, "remove", PUBLIC_IDEA_ID, IDEA_ID, "--type", "related_to"],
    )
    assert removed.exit_code == 0
    assert runner.invoke(app, [*base, "list", PUBLIC_IDEA_ID]).stdout.endswith("0 relation(s).\n")
