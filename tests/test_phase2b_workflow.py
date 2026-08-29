from __future__ import annotations

from pathlib import Path

import pytest
from test_phase2b_capture import Repositories, Zotero
from typer.testing import CliRunner

from knowlume.adapters.filesystem import FilesystemVault
from knowlume.application.capture import UnifiedCaptureService
from knowlume.application.notes import NoteService
from knowlume.application.scanning import scan_vault
from knowlume.cli import app

ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
runner = CliRunner()


def test_repository_capture_then_literature_note_is_one_explicit_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filesystem = FilesystemVault(environment={})
    vault = filesystem.initialize(tmp_path / "vault", CONFIG)
    capture = UnifiedCaptureService(
        filesystem=filesystem,
        zotero=Zotero({}),
        repositories=Repositories(),
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8G0",
    )
    source = capture.add(vault, "https://github.com/acme/project", "repo")
    before = scan_vault(vault)
    assert len(before.objects) == 1 and not before.relation_shards

    note = NoteService(
        filesystem=filesystem,
        template_reader=lambda name: (ROOT / name).read_text(encoding="utf-8"),
        ulid_factory=lambda: "01JSTAG7N9Q3V5X8Y2Z4A6B8G1",
    )
    monkeypatch.setattr("knowlume.cli._note_service", lambda: note)
    created = runner.invoke(
        app,
        [
            "--vault",
            str(vault.root),
            "note",
            "new",
            "--type",
            "literature",
            "--source",
            str(source.source_id),
        ],
    )
    assert created.exit_code == 0
    accepted = scan_vault(vault)
    assert accepted.healthy and len(accepted.objects) == 2
    assert len(accepted.relation_shards) == 1
    relations = next(iter(accepted.relation_shards.values())).shard.relations
    assert len(relations) == 1 and relations[0].relation_type.value == "summarizes"
    assert str(relations[0].to_id) == str(source.source_id)
