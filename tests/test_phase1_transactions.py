from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from knowlume.adapters.filesystem import FilesystemVault, checksum_bytes, load_vault
from knowlume.adapters.transactions import RecoverableTransactions, WriteRequest
from knowlume.domain.values import DomainError

ROOT = Path(__file__).resolve().parents[1]
CONFIG_TEXT = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")


class SimulatedCrash(BaseException):
    pass


def _vault(tmp_path: Path):  # type: ignore[no-untyped-def]
    root = tmp_path / "vault"
    FilesystemVault(environment={}).initialize(root, CONFIG_TEXT)
    return load_vault(root)


def _writes(vault) -> tuple[WriteRequest, WriteRequest]:  # type: ignore[no-untyped-def]
    existing = vault.root / "notes" / "ideas" / "existing.md"
    existing.write_bytes(b"original\n")
    return (
        WriteRequest(
            "notes/ideas/existing.md",
            b"replacement\n",
            checksum_bytes(b"original\n"),
        ),
        WriteRequest("relations/new.yaml", b"relations: []\n", None),
    )


def test_multi_file_transaction_commits_and_cleans_up(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    checksums = RecoverableTransactions().commit(vault, "migration", _writes(vault))
    assert checksums == (
        checksum_bytes(b"replacement\n"),
        checksum_bytes(b"relations: []\n"),
    )
    assert (vault.root / "notes/ideas/existing.md").read_bytes() == b"replacement\n"
    assert (vault.root / "relations/new.yaml").read_bytes() == b"relations: []\n"
    assert list((vault.root / ".knowlume/transactions").iterdir()) == []
    assert not (vault.root / ".knowlume/locks/vault-write.lock").exists()


CRASH_POINTS = [
    "after-preparing",
    "after-stage-0",
    "after-stage-1",
    "after-prepared",
    "after-committing",
    "before-entry-0",
    "after-backup-0",
    "after-replace-0",
    "after-entry-0",
    "before-entry-1",
    "after-backup-1",
    "after-replace-1",
    "after-entry-1",
    "after-committed",
]


@pytest.mark.parametrize("crash_point", CRASH_POINTS)
def test_recovery_is_deterministic_at_every_commit_boundary(
    tmp_path: Path, crash_point: str
) -> None:
    vault = _vault(tmp_path)
    writes = _writes(vault)

    def interrupt(point: str) -> None:
        if point == crash_point:
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        RecoverableTransactions().commit(vault, "migration", writes, interrupt=interrupt)
    outcome = RecoverableTransactions(process_alive=lambda _: False).recover(vault)
    if crash_point == "after-committed":
        assert outcome == "committed"
        assert (vault.root / "notes/ideas/existing.md").read_bytes() == b"replacement\n"
        assert (vault.root / "relations/new.yaml").read_bytes() == b"relations: []\n"
    else:
        assert outcome == "rolled-back"
        assert (vault.root / "notes/ideas/existing.md").read_bytes() == b"original\n"
        assert not (vault.root / "relations/new.yaml").exists()
    assert RecoverableTransactions(process_alive=lambda _: False).recover(vault) == "clean"


def test_regular_failure_rolls_back_before_returning(tmp_path: Path) -> None:
    vault = _vault(tmp_path)

    def interrupt(point: str) -> None:
        if point == "after-replace-0":
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected"):
        RecoverableTransactions().commit(vault, "migration", _writes(vault), interrupt=interrupt)
    assert (vault.root / "notes/ideas/existing.md").read_bytes() == b"original\n"
    assert not (vault.root / "relations/new.yaml").exists()


@pytest.mark.parametrize(
    "recovery_point",
    ["after-rolling-back", "after-restore-1", "after-restore-0", "after-rolled-back"],
)
def test_recovery_can_resume_at_every_rollback_boundary(
    tmp_path: Path, recovery_point: str
) -> None:
    vault = _vault(tmp_path)

    def commit_interrupt(point: str) -> None:
        if point == "after-entry-1":
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        RecoverableTransactions().commit(
            vault, "migration", _writes(vault), interrupt=commit_interrupt
        )

    def recovery_interrupt(point: str) -> None:
        if point == recovery_point:
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        RecoverableTransactions(process_alive=lambda _: False).recover(
            vault, interrupt=recovery_interrupt
        )
    outcome = RecoverableTransactions(process_alive=lambda _: False).recover(vault)
    assert outcome == "rolled-back"
    assert (vault.root / "notes/ideas/existing.md").read_bytes() == b"original\n"
    assert not (vault.root / "relations/new.yaml").exists()


def test_transaction_verifies_all_checksums_before_replacement(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    writes = list(_writes(vault))
    writes[1] = WriteRequest("relations/new.yaml", b"new", checksum_bytes(b"missing"))
    with pytest.raises(DomainError) as caught:
        RecoverableTransactions().commit(vault, "migration", writes)
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    assert (vault.root / "notes/ideas/existing.md").read_bytes() == b"original\n"


def test_lock_contention_blocks_a_simultaneous_writer(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    prepared = threading.Event()
    release = threading.Event()

    def interrupt(point: str) -> None:
        if point == "after-prepared":
            prepared.set()
            assert release.wait(timeout=5)

    def first_writer() -> None:
        RecoverableTransactions().commit(vault, "migration", _writes(vault), interrupt=interrupt)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(first_writer)
        assert prepared.wait(timeout=5)
        with pytest.raises(DomainError) as caught:
            RecoverableTransactions().commit(
                vault,
                "migration",
                [WriteRequest("relations/second.yaml", b"second", None)],
            )
        assert caught.value.code == "VAULT_LOCKED"
        release.set()
        future.result(timeout=5)


def test_single_file_write_detects_unfinished_transaction(tmp_path: Path) -> None:
    vault = _vault(tmp_path)

    def interrupt(point: str) -> None:
        if point == "after-prepared":
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        RecoverableTransactions().commit(vault, "migration", _writes(vault), interrupt=interrupt)
    lock = vault.root / ".knowlume/locks/vault-write.lock"
    lock.unlink()
    with pytest.raises(DomainError) as caught:
        FilesystemVault(environment={}).atomic_write(vault, "notes/ideas/other.md", b"other", None)
    assert caught.value.code == "VAULT_RECOVERY_REQUIRED"


def test_unsupported_manifest_and_malformed_lock_fail_closed(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    transactions = vault.root / ".knowlume/transactions"
    transaction = transactions / "txn_01JSTAG7N9Q3V5X8Y2Z4A6B8D2"
    transaction.mkdir()
    manifest = {
        "transaction_version": 99,
        "transaction_id": transaction.name,
        "operation": "migration",
        "state": "prepared",
        "created_at": "2026-08-27T00:00:00+00:00",
        "updated_at": "2026-08-27T00:00:00+00:00",
        "entries": [],
    }
    (transaction / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DomainError) as caught:
        RecoverableTransactions(process_alive=lambda _: False).recover(vault)
    assert caught.value.code == "VAULT_RECOVERY_FAILED"

    manifest["transaction_version"] = 1
    (transaction / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (vault.root / ".knowlume/locks/vault-write.lock").write_text("not json", encoding="utf-8")
    with pytest.raises(DomainError) as caught:
        RecoverableTransactions(process_alive=lambda _: False).recover(vault)
    assert caught.value.code == "VAULT_RECOVERY_FAILED"
