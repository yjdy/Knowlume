from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.adapters.filesystem import FilesystemVault, checksum_file
from knowlume.application.ai import AIService
from knowlume.application.scanning import scan_vault
from knowlume.cli import app
from knowlume.domain.values import ArtifactType, DomainError, ObjectId, RecordStatus, ReviewStatus
from knowlume.ports.vault import Vault

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ID = "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E1"
NOTE_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D0"
NOW = datetime(2026, 9, 11, 8, tzinfo=UTC)
runner = CliRunner()


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    vault = FilesystemVault(environment={}).initialize(
        tmp_path / "vault", (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
    )
    for fixture, target in [
        ("unreviewed-ai-artifact.md", "ai/artifacts/candidate.md"),
        ("idea-note.md", "notes/ideas/idea.md"),
    ]:
        (vault.root / target).write_bytes((ROOT / "tests/fixtures/v2/valid" / fixture).read_bytes())
    assert scan_vault(vault).healthy
    return vault


def snapshot(vault: Vault) -> dict[str, bytes]:
    return {
        p.relative_to(vault.root).as_posix(): p.read_bytes()
        for p in vault.root.rglob("*")
        if p.is_file()
    }


def checksum(vault: Vault, path: str) -> str:
    result = checksum_file(vault.root / path)
    assert result is not None
    return result


def service() -> AIService:
    return AIService(clock=lambda: NOW)


def change_artifact(vault: Vault, **changes: Any) -> None:
    path = vault.root / "ai/artifacts/candidate.md"
    document = parse_object_document(path.read_text(encoding="utf-8"))
    path.write_text(
        render_object_document(replace(document, object=replace(document.object, **changes))),
        encoding="utf-8",
    )


@pytest.mark.parametrize("artifact_type", list(ArtifactType))
@pytest.mark.parametrize("state", list(ReviewStatus))
def test_queue_all_types_states_filters_and_stable_pagination(
    vault: Vault, artifact_type: ArtifactType, state: ReviewStatus
) -> None:
    change_artifact(
        vault,
        artifact_type=artifact_type,
        review_status=state,
        reviewed_by=None if state is ReviewStatus.UNREVIEWED else "old-reviewer",
        reviewed_at=None if state is ReviewStatus.UNREVIEWED else NOW,
    )
    original = vault.root / "ai/artifacts/candidate.md"
    second_id = "ai_01JSTAG7N9Q3V5X8Y2Z4A6B8E2"
    doc = parse_object_document(original.read_text(encoding="utf-8"))
    (vault.root / "ai/artifacts/second.md").write_text(
        render_object_document(replace(doc, object=replace(doc.object, id=ObjectId(second_id)))),
        encoding="utf-8",
    )
    before = snapshot(vault)
    page = service().list(
        vault, review_status=state.value, artifact_type=artifact_type.value, limit=1, offset=1
    )
    assert page["total"] == 2 and len(page["items"]) == 1
    assert page["items"][0]["object_id"] == second_id
    assert "body" not in page["items"][0] and "input_refs" not in page["items"][0]
    assert service().list(vault)["total"] == (2 if state is ReviewStatus.UNREVIEWED else 0)
    assert service().list(vault, review_status="all", offset=2)["items"] == []
    assert snapshot(vault) == before
    change_artifact(vault, record_status=RecordStatus.ARCHIVED)
    assert service().list(vault, review_status="all")["total"] == 1
    assert service().list(vault, review_status="all", status="all")["total"] == 2


@pytest.mark.parametrize(
    "options", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"review_status": "unknown"}]
)
def test_queue_rejects_invalid_bounds_without_writes(vault: Vault, options: dict[str, Any]) -> None:
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        service().list(vault, **options)
    assert caught.value.code == "AI_ARGUMENT_INVALID"
    assert snapshot(vault) == before


def test_queue_empty_success_and_broken_file_failure_are_distinct(vault: Vault) -> None:
    path = vault.root / "ai/artifacts/candidate.md"
    path.unlink()
    assert service().list(vault)["total"] == 0
    path.write_text("not an Artifact", encoding="utf-8")
    with pytest.raises(DomainError) as caught:
        service().list(vault)
    assert caught.value.code == "VAULT_INVALID"


def test_ai_cli_list_checkpoint(vault: Vault) -> None:
    before = snapshot(vault)
    result = runner.invoke(app, ["--vault", str(vault.root), "ai", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["total"] == 1
    assert snapshot(vault) == before
