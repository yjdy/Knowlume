from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.adapters.filesystem import FilesystemVault, checksum_file
from knowlume.adapters.transactions import RecoverableTransactions, WriteRequest
from knowlume.application.ai import AIService, artifact_digest
from knowlume.application.scanning import scan_vault
from knowlume.cli import app
from knowlume.domain.models import AIArtifact, AIBlock, NoteBody
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


def review(
    vault: Vault, *, decision: str = "accepted", target: AIService | None = None
) -> dict[str, object]:
    return (target or service()).review(
        vault,
        ARTIFACT_ID,
        decision=decision,
        reviewer="reviewer",
        expected_checksum=checksum(vault, "ai/artifacts/candidate.md"),
    )


def promote(
    vault: Vault, *, apply: bool = False, target: AIService | None = None, **overrides: str
) -> dict[str, object]:
    arguments = {
        "note_id": NOTE_ID,
        "section_id": "sec_reviewed_ai",
        "actor": "promoter",
        "expected_artifact_checksum": checksum(vault, "ai/artifacts/candidate.md"),
        "expected_note_checksum": checksum(vault, "notes/ideas/idea.md"),
    } | overrides
    return (target or service()).promote(vault, ARTIFACT_ID, apply=apply, **arguments)


def change_artifact(vault: Vault, **changes: Any) -> None:
    path = vault.root / "ai/artifacts/candidate.md"
    document = parse_object_document(path.read_text(encoding="utf-8"))
    path.write_text(
        render_object_document(replace(document, object=replace(document.object, **changes))),
        encoding="utf-8",
    )


def test_review_preview_apply_and_retry_are_durable_and_faithful(vault: Vault) -> None:
    before = snapshot(vault)
    queue = service().list(vault)
    assert queue["total"] == 1
    assert snapshot(vault) == before
    result = review(vault)
    assert result["changed"] is True
    accepted = snapshot(vault)
    assert review(vault)["changed"] is False
    assert snapshot(vault) == accepted
    dry_run = promote(vault)
    assert dry_run["mode"] == "dry-run" and dry_run["changed"] is False
    assert snapshot(vault) == accepted
    applied = promote(vault, apply=True)
    assert applied["changed"] is True and applied["already_promoted"] is False
    complete = snapshot(vault)
    assert promote(vault, apply=True)["already_promoted"] is True
    assert snapshot(vault) == complete
    scan = scan_vault(vault)
    assert scan.healthy
    artifact = scan.objects[ObjectId(ARTIFACT_ID)].document.object
    assert isinstance(artifact, AIArtifact)
    assert artifact.review_status is ReviewStatus.PROMOTED
    assert artifact.reviewed_by == "reviewer" and artifact.promotion is not None
    assert artifact.promotion.actor_id == "promoter"
    note = scan.objects[ObjectId(NOTE_ID)].document.body
    assert isinstance(note, NoteBody)
    assert note.sections[-1].blocks == (
        AIBlock("# Unreviewed candidate\n\nPrivate unreviewed candidate.", ObjectId(ARTIFACT_ID)),
    )
    original = parse_object_document(before["notes/ideas/idea.md"].decode("utf-8")).body
    assert isinstance(original, NoteBody) and note.sections[:-1] == original.sections
    assert all("kb.sqlite" not in p for p in complete)


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_review_decisions_preserve_body_and_noop_time(vault: Vault, decision: str) -> None:
    before = parse_object_document(
        (vault.root / "ai/artifacts/candidate.md").read_text(encoding="utf-8")
    )
    review(vault, decision=decision)
    after = parse_object_document(
        (vault.root / "ai/artifacts/candidate.md").read_text(encoding="utf-8")
    )
    assert before.body == after.body
    assert artifact_digest(before) == artifact_digest(after)
    state = snapshot(vault)
    assert review(vault, decision=decision)["changed"] is False
    assert snapshot(vault) == state


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


def test_legacy_accepted_re_review_retains_prior_attribution(vault: Vault) -> None:
    change_artifact(
        vault, review_status=ReviewStatus.ACCEPTED, reviewed_by="legacy", reviewed_at=NOW
    )
    with pytest.raises(DomainError, match="evidence"):
        promote(vault, apply=True)
    review(vault)
    artifact = scan_vault(vault).objects[ObjectId(ARTIFACT_ID)].document.object
    assert isinstance(artifact, AIArtifact) and artifact.review_evidence is not None
    assert artifact.review_evidence.prior_review is not None
    assert artifact.review_evidence.prior_review.reviewed_by == "legacy"


@pytest.mark.parametrize("state", ["unreviewed", "rejected"])
def test_unaccepted_promotion_refused_without_writes(vault: Vault, state: str) -> None:
    if state == "rejected":
        review(vault, decision="rejected")
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True)
    assert caught.value.code == "AI_STATE_INVALID"
    assert snapshot(vault) == before


def test_reviewed_body_change_requires_new_candidate(vault: Vault) -> None:
    review(vault)
    path = vault.root / "ai/artifacts/candidate.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nChanged candidate.\n", encoding="utf-8")
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True)
    assert caught.value.code == "AI_REVIEW_EVIDENCE_INVALID"
    assert snapshot(vault) == before


def test_target_input_can_be_promoted_then_retried(vault: Vault) -> None:
    from knowlume.domain.models import InputRef

    change_artifact(vault, input_refs=(InputRef(ObjectId(NOTE_ID)),))
    review(vault)
    promote(vault, apply=True)
    assert promote(vault, apply=True)["already_promoted"] is True
    path = vault.root / "notes/ideas/idea.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nHuman edit.\n", encoding="utf-8")
    before = snapshot(vault)
    with pytest.raises(DomainError):
        promote(vault, apply=True)
    assert snapshot(vault) == before


def test_input_revision_changes_invalidate_accepted_review(vault: Vault) -> None:
    from knowlume.domain.models import InputRef

    change_artifact(vault, input_refs=(InputRef(ObjectId(NOTE_ID)),))
    review(vault)
    path = vault.root / "notes/ideas/idea.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nNew input.\n", encoding="utf-8")
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True)
    assert caught.value.code == "AI_INPUT_CHANGED"
    assert snapshot(vault) == before


class InterruptedTransactions(RecoverableTransactions):
    def __init__(self, event: str, *, crash: bool = False) -> None:
        super().__init__()
        self.event, self.crash = event, crash

    def commit(
        self,
        vault: Vault,
        operation: str,
        writes: Sequence[WriteRequest],
        *,
        interrupt: Callable[[str], None] | None = None,
        validate_reads: Callable[[Mapping[str, str]], None] | None = None,
    ) -> tuple[str, ...]:
        def fail(event: str) -> None:
            if event == self.event:
                if self.crash:
                    raise KeyboardInterrupt("simulated process interruption")
                raise RuntimeError("simulated failure")

        return super().commit(
            vault, operation, writes, interrupt=fail, validate_reads=validate_reads
        )


@pytest.mark.parametrize(
    "event",
    [
        "after-preparing",
        "after-stage-0",
        "after-prepared",
        "after-committing",
        *[
            f"{point}-{index}"
            for index in range(3)
            for point in ("before-entry", "after-backup", "after-replace", "after-entry")
        ],
    ],
)
@pytest.mark.parametrize("crash", [False, True])
def test_promotion_failure_and_interruption_recover_original_files(
    vault: Vault, event: str, crash: bool
) -> None:
    review(vault)
    before = snapshot(vault)
    broken = AIService(transactions=InterruptedTransactions(event, crash=crash), clock=lambda: NOW)
    with pytest.raises((RuntimeError, KeyboardInterrupt)):
        promote(vault, apply=True, target=broken)
    if crash:
        recovery = RecoverableTransactions(process_alive=lambda _: False)
        assert recovery.recover(vault) == "rolled-back"
        assert recovery.recover(vault) == "clean"
    assert snapshot(vault) == before
    assert promote(vault, apply=True)["changed"] is True


@pytest.mark.parametrize(
    "arguments",
    [["list", "--limit", "bad"], ["review"], ["promote", ARTIFACT_ID], ["list", "--unknown"]],
)
def test_ai_cli_usage_failures_emit_single_envelope(arguments: list[str]) -> None:
    result = runner.invoke(app, ["ai", *arguments, "--json"])
    assert result.exit_code == 2, result.output
    document = json.loads(result.stdout)
    assert document["success"] is False and document["exit_code"] == 2
    assert document["errors"][0]["code"] == "AI_ARGUMENT_INVALID"


def test_ai_cli_list_and_review(vault: Vault) -> None:
    args = ["--vault", str(vault.root), "ai"]
    result = runner.invoke(app, [*args, "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["total"] == 1
    result = runner.invoke(
        app,
        [
            *args,
            "review",
            ARTIFACT_ID,
            "--decision",
            "accepted",
            "--reviewer",
            "reviewer",
            "--expect-checksum",
            checksum(vault, "ai/artifacts/candidate.md"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["review_status"] == "accepted"


def test_json_flag_consumed_as_reviewer_never_becomes_human_attribution(vault: Vault) -> None:
    before = snapshot(vault)
    result = runner.invoke(
        app,
        [
            "--vault",
            str(vault.root),
            "ai",
            "review",
            ARTIFACT_ID,
            "--decision",
            "accepted",
            "--expect-checksum",
            checksum(vault, "ai/artifacts/candidate.md"),
            "--reviewer",
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["errors"][0]["code"] == "AI_ARGUMENT_INVALID"
    assert snapshot(vault) == before
