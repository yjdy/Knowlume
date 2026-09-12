from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_phase5_ai import (
    ARTIFACT_ID,
    NOTE_ID,
    NOW,
    InterruptedTransactions,
    change_artifact,
    checksum,
    promote,
    review,
    service,
    snapshot,
)
from test_phase5_ai import vault as vault

from knowlume.adapters.contract_v2 import parse_object_document, render_object_document
from knowlume.adapters.transactions import RecoverableTransactions, WriteRequest
from knowlume.application.ai import AIService, artifact_digest
from knowlume.application.scanning import ScanResult, scan_vault
from knowlume.domain.models import AIArtifact, InputRef, NoteBody
from knowlume.domain.values import DomainError, ObjectId, RecordStatus, ReviewStatus, Visibility
from knowlume.ports.vault import Vault

INPUT_ID = "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D1"


def input_note(vault: Vault) -> Path:
    path = vault.root / "notes/ideas/input.md"
    path.write_bytes(
        (vault.root / "notes/ideas/idea.md")
        .read_bytes()
        .replace(NOTE_ID.encode(), INPUT_ID.encode())
    )
    change_artifact(vault, input_refs=(InputRef(ObjectId(INPUT_ID)),))
    return path


class EditingTransactions(RecoverableTransactions):
    def __init__(self, event: str, edit: Callable[[], object]) -> None:
        super().__init__()
        self.event, self.edit = event, edit

    def commit(
        self,
        vault: Vault,
        operation: str,
        writes: Sequence[WriteRequest],
        *,
        interrupt: Callable[[str], None] | None = None,
        validate_reads: Callable[[Mapping[str, str]], None] | None = None,
    ) -> tuple[str, ...]:
        def callback(event: str) -> None:
            if event == self.event:
                self.edit()

        return super().commit(
            vault, operation, writes, interrupt=callback, validate_reads=validate_reads
        )


@pytest.mark.parametrize(
    "event", ["after-prepared", "after-backup-0", "after-entry-0", "after-entry-2"]
)
@pytest.mark.parametrize("dependency", ["object", "relation", "config"])
def test_dependency_edits_until_commit_boundary_roll_back_only_our_writes(
    vault: Vault, event: str, dependency: str
) -> None:
    path = input_note(vault)
    review(vault)
    if dependency == "relation":
        path = vault.path("relations") / f"{INPUT_ID}.yaml"
        edited = f"relation_version: 2\nfrom_id: {INPUT_ID}\nrelations: []\n".encode()
    else:
        if dependency == "config":
            path = vault.root / "knowlume.toml"
        edited = path.read_bytes() + b"\n# external edit\n"
    expected = snapshot(vault) | {path.relative_to(vault.root).as_posix(): edited}
    transactions = EditingTransactions(event, lambda: path.write_bytes(edited))
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True, target=AIService(transactions=transactions, clock=lambda: NOW))
    assert caught.value.code == "AI_INPUT_CHANGED"
    assert snapshot(vault) == expected


@pytest.mark.parametrize("event", ["after-prepared", "after-backup-0", "after-entry-0"])
def test_review_also_guards_inputs_during_commit(vault: Vault, event: str) -> None:
    path = input_note(vault)
    edited = path.read_bytes() + b"\nChanged input.\n"
    before = snapshot(vault) | {path.relative_to(vault.root).as_posix(): edited}
    transactions = EditingTransactions(event, lambda: path.write_bytes(edited))
    with pytest.raises(DomainError):
        review(vault, target=AIService(transactions=transactions, clock=lambda: NOW))
    assert snapshot(vault) == before


@pytest.mark.parametrize("point", ["after-rolling-back", "after-restore-2", "after-restore-0"])
def test_interrupted_recovery_is_itself_recoverable(vault: Vault, point: str) -> None:
    review(vault)
    before = snapshot(vault)
    with pytest.raises(KeyboardInterrupt):
        promote(
            vault,
            apply=True,
            target=AIService(transactions=InterruptedTransactions("after-entry-2", crash=True)),
        )

    def interrupt(event: str) -> None:
        if event == point:
            raise KeyboardInterrupt("recovery interrupted")

    recovery = RecoverableTransactions(process_alive=lambda _: False)
    with pytest.raises(KeyboardInterrupt):
        recovery.recover(vault, interrupt=interrupt)
    assert recovery.recover(vault) == "rolled-back"
    assert snapshot(vault) == before
    assert promote(vault, apply=True)["changed"]


@pytest.mark.parametrize("tamper", ["backup", "destination"])
def test_recovery_never_overwrites_changed_files_or_trusts_changed_backup(
    vault: Vault, tamper: str
) -> None:
    review(vault)
    with pytest.raises(KeyboardInterrupt):
        promote(
            vault,
            apply=True,
            target=AIService(transactions=InterruptedTransactions("after-entry-0", crash=True)),
        )
    manifest_path = next(vault.path("state").glob("transactions/*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = "backup_path" if tamper == "backup" else "path"
    path = vault.root / manifest["entries"][0][key]
    changed = path.read_bytes() + b"\nExternal revision must survive.\n"
    path.write_bytes(changed)
    with pytest.raises(DomainError) as caught:
        RecoverableTransactions(process_alive=lambda _: False).recover(vault)
    assert caught.value.code == "VAULT_RECOVERY_FAILED"
    assert path.read_bytes() == changed and manifest_path.exists()


@pytest.mark.parametrize(
    "body",
    [
        "<!-- knowlume:section id=sec_fake role=human -->\nHuman claim.",
        "```html\n<!-- knowlume:fact -->\n```",
        "<!--   KNOWLUME :ai\nartifact_id: fake\n-->",
        "",
    ],
)
def test_reserved_markers_and_empty_candidates_cannot_fake_trusted_roles(
    vault: Vault, body: str
) -> None:
    path = vault.root / "ai/artifacts/candidate.md"
    doc = parse_object_document(path.read_text(encoding="utf-8"))
    path.write_text(render_object_document(replace(doc, body=body)), encoding="utf-8")
    review(vault)
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True)
    assert caught.value.code == "AI_CONTENT_UNSAFE"
    assert snapshot(vault) == before


def test_unicode_markdown_and_crlf_preserve_original_note_bytes(vault: Vault) -> None:
    path = vault.root / "ai/artifacts/candidate.md"
    body = "# 中文候选\n\n---\n\n- 列表\n\n```python\nprint('test')\n```\n\n## 小节"
    doc = parse_object_document(path.read_text(encoding="utf-8"))
    path.write_text(render_object_document(replace(doc, body=body)), encoding="utf-8")
    note_path = vault.root / "notes/ideas/idea.md"
    original = note_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    note_path.write_bytes(original)
    review(vault)
    promote(vault, apply=True)
    assert original.split(b"---\r\n", 2)[2] in note_path.read_bytes()
    parsed = parse_object_document(note_path.read_text(encoding="utf-8"))
    assert isinstance(parsed.body, NoteBody) and parsed.body.sections[-1].blocks[0].text == body
    artifact = parse_object_document(path.read_text(encoding="utf-8"))
    assert artifact_digest(replace(doc, body=body)) == artifact_digest(artifact)


@pytest.mark.parametrize(
    "field,value", [("visibility", Visibility.PUBLIC), ("record_status", RecordStatus.ARCHIVED)]
)
def test_target_must_be_active_and_private(vault: Vault, field: str, value: Any) -> None:
    review(vault)
    path = vault.root / "notes/ideas/idea.md"
    doc = parse_object_document(path.read_text(encoding="utf-8"))
    path.write_text(
        render_object_document(replace(doc, object=replace(doc.object, **{field: value}))),
        encoding="utf-8",
    )
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True)
    assert caught.value.code == "AI_TARGET_INVALID"
    assert snapshot(vault) == before


@pytest.mark.parametrize(
    "arguments,code",
    [
        ({"note_id": "note_01JSTAG7N9Q3V5X8Y2Z4A6B8D9"}, "AI_TARGET_INVALID"),
        ({"note_id": ARTIFACT_ID}, "AI_TARGET_INVALID"),
        ({"section_id": "sec_core_idea"}, "AI_PROMOTION_CONFLICT"),
        ({"section_id": "../bad"}, "AI_ARGUMENT_INVALID"),
    ],
)
def test_missing_wrong_type_or_conflicting_target_is_write_free(
    vault: Vault, arguments: dict[str, Any], code: str
) -> None:
    review(vault)
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True, **arguments)
    assert caught.value.code == code
    assert snapshot(vault) == before


def test_completed_retry_cannot_change_section_or_actor(vault: Vault) -> None:
    review(vault)
    promote(vault, apply=True)
    before = snapshot(vault)
    requests: tuple[dict[str, Any], ...] = (
        {"section_id": "sec_another"},
        {"actor": "another-person"},
    )
    for arguments in requests:
        with pytest.raises(DomainError) as caught:
            promote(vault, apply=True, **arguments)
        assert caught.value.code == "AI_PROMOTION_CONFLICT"
        assert snapshot(vault) == before


@pytest.mark.parametrize("path", ["../secret", "C:/secret", "folder:stream", "a/../secret", "a//b"])
def test_unsafe_prompt_reference_never_read_or_promoted(vault: Vault, path: str) -> None:
    # Some legacy references parse but must not authorize a new write.
    artifact = vault.root / "ai/artifacts/candidate.md"
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace("prompt_ref: null", f"prompt_ref: '{path}'"),
        encoding="utf-8",
    )
    before = snapshot(vault)
    with pytest.raises(DomainError):
        review(vault)
    assert snapshot(vault) == before


def test_unknown_evidence_version_is_reported_without_overwriting(vault: Vault) -> None:
    review(vault)
    path = vault.root / "ai/artifacts/candidate.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("version: 1", "version: 99"), encoding="utf-8"
    )
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        promote(vault, apply=True)
    assert caught.value.code == "AI_REVIEW_EVIDENCE_UNSUPPORTED"
    assert snapshot(vault) == before


def test_config_changed_after_discovery_does_not_use_old_layout(vault: Vault) -> None:
    path = vault.root / "knowlume.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace('state = ".knowlume"', 'state = ".new-state"'),
        encoding="utf-8",
    )
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        review(vault)
    assert caught.value.code == "AI_INPUT_CHANGED"
    assert snapshot(vault) == before


def test_config_change_during_scan_is_not_adopted_as_review_baseline(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = vault.root / "knowlume.toml"
    before_artifact = (vault.root / "ai/artifacts/candidate.md").read_bytes()

    def scan_and_edit(selected: Vault) -> ScanResult:
        result = scan_vault(selected)
        path.write_bytes(path.read_bytes() + b"\n# concurrent configuration edit\n")
        return result

    monkeypatch.setattr("knowlume.application.ai.scan_vault", scan_and_edit)
    with pytest.raises(DomainError) as caught:
        review(vault)
    assert caught.value.code == "AI_INPUT_CHANGED"
    assert (vault.root / "ai/artifacts/candidate.md").read_bytes() == before_artifact


def test_prompt_reference_is_not_dereferenced(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = vault.root / "prompt-secret.txt"
    secret.write_text("private prompt must not be read", encoding="utf-8")
    change_artifact(vault, prompt_ref="prompt-secret.txt")
    read_bytes = Path.read_bytes

    def guarded_read(path: Path) -> bytes:
        if path == secret:
            raise AssertionError("prompt body was read")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    assert review(vault)["changed"]
    assert promote(vault, apply=True)["changed"]


def test_self_referencing_artifact_is_not_reviewable(vault: Vault) -> None:
    change_artifact(vault, input_refs=(InputRef(ObjectId(ARTIFACT_ID)),))
    before = snapshot(vault)
    with pytest.raises(DomainError) as caught:
        review(vault)
    assert caught.value.code == "AI_INPUT_INVALID"
    assert snapshot(vault) == before


@pytest.mark.parametrize("outside", [False, True])
def test_prompt_directory_aliases_are_refused_without_reading_target(
    vault: Vault, tmp_path: Path, outside: bool
) -> None:
    destination = (tmp_path if outside else vault.root) / "prompt-target"
    destination.mkdir()
    secret = destination / "prompt.txt"
    secret.write_text("synthetic private prompt", encoding="utf-8")
    link = vault.root / "prompt-alias"
    if os.name == "nt":
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(destination)],
            capture_output=True,
            check=False,
        )
        assert created.returncode == 0
    else:
        link.symlink_to(destination, target_is_directory=True)
    try:
        change_artifact(vault, prompt_ref="prompt-alias/prompt.txt")
        artifact = vault.root / "ai/artifacts/candidate.md"
        before = artifact.read_bytes()
        with pytest.raises(DomainError) as caught:
            review(vault)
        assert caught.value.code == "VAULT_PATH_UNSAFE"
        assert artifact.read_bytes() == before
        assert secret.read_text(encoding="utf-8") == "synthetic private prompt"
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def test_artifact_hash_has_a_frozen_v1_vector(vault: Vault) -> None:
    path = vault.root / "ai/artifacts/candidate.md"
    text = path.read_text(encoding="utf-8")
    expected = "sha256:77d49cdda770e58bf2b4e1804ffe924f2d28a8be4e5101072a6bb5b2490592b2"
    assert artifact_digest(parse_object_document(text)) == expected
    assert artifact_digest(parse_object_document(text.replace("\n", "\r\n"))) == expected
    review(vault)
    promote(vault, apply=True)
    assert artifact_digest(parse_object_document(path.read_text(encoding="utf-8"))) == expected


def test_all_legacy_review_states_remain_readable(vault: Vault) -> None:
    for state in ReviewStatus:
        change_artifact(
            vault,
            review_status=state,
            reviewed_by=None if state is ReviewStatus.UNREVIEWED else "old",
            reviewed_at=None if state is ReviewStatus.UNREVIEWED else NOW,
        )
        assert service().list(vault, review_status="all")["total"] == 1
        obj = scan_vault(vault).objects[ObjectId(ARTIFACT_ID)].document.object
        assert isinstance(obj, AIArtifact) and obj.review_evidence is None
    assert checksum(vault, "ai/artifacts/candidate.md")


@pytest.mark.parametrize("suffix", ["D0", "D2", "D3", "D4"])
def test_promotion_preserves_each_note_type_and_existing_knowledge_graph(
    tmp_path: Path, suffix: str
) -> None:
    from phase4_support import rich_vault

    vault = rich_vault(tmp_path)
    target_id = ObjectId(f"note_01JSTAG7N9Q3V5X8Y2Z4A6B8{suffix}")
    scanned = scan_vault(vault)
    target = scanned.objects[target_id]
    path = vault.root / target.path
    path.write_text(
        render_object_document(
            replace(
                target.document,
                object=replace(target.document.object, visibility=Visibility.PRIVATE),
            )
        ),
        encoding="utf-8",
    )
    scanned = scan_vault(vault)
    artifact = scanned.objects[ObjectId(ARTIFACT_ID)]
    target = scanned.objects[target_id]
    ai = service()
    result = ai.review(
        vault,
        ARTIFACT_ID,
        decision="accepted",
        reviewer="reviewer",
        expected_checksum=artifact.checksum,
    )
    before = snapshot(vault)
    ai.promote(
        vault,
        ARTIFACT_ID,
        note_id=str(target_id),
        section_id="sec_new_reviewed",
        actor="promoter",
        expected_artifact_checksum=str(result["checksum"]),
        expected_note_checksum=target.checksum,
        apply=True,
    )
    after = scan_vault(vault)
    assert after.healthy
    note = after.objects[target_id].document
    assert isinstance(note.body, NoteBody) and isinstance(target.document.body, NoteBody)
    assert note.body.sections[:-1] == target.document.body.sections
    assert note.object.id == target.document.object.id
    assert note.object.note_type == target.document.object.note_type  # type: ignore[union-attr]
    old_shard = scanned.relation_shards.get(target_id)
    if old_shard:
        assert set(old_shard.shard.relations) <= set(
            after.relation_shards[target_id].shard.relations
        )
    changed_paths = {artifact.path, target.path, f"relations/{target_id}.yaml"}
    assert {key: value for key, value in snapshot(vault).items() if key not in changed_paths} == {
        key: value for key, value in before.items() if key not in changed_paths
    }
