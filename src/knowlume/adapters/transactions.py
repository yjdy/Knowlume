from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from knowlume.adapters.filesystem import checksum_bytes, checksum_file
from knowlume.constants import TRANSACTION_VERSION
from knowlume.domain.values import DomainError
from knowlume.ids import new_ulid
from knowlume.ports.vault import Vault

TRANSACTION_RE = re.compile(r"^txn_[0-9A-HJKMNP-TV-Z]{26}$")
MANIFEST_STATES = {
    "preparing",
    "prepared",
    "committing",
    "rolling_back",
    "committed",
    "rolled_back",
}
ENTRY_STATES = {"pending", "backed_up", "replaced", "restored"}


@dataclass(frozen=True)
class WriteRequest:
    path: str
    content: bytes
    expected_checksum: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise DomainError("VAULT_PATH_UNSAFE", "transaction path is not Vault-relative")
    return path


def _destination(vault: Vault, value: str) -> Path:
    relative = _relative_path(value)
    target = vault.root.joinpath(*relative.parts)
    try:
        parent = target.parent.resolve(strict=True)
    except OSError as error:
        raise DomainError("VAULT_PATH_UNSAFE", "transaction parent does not exist") from error
    if not _inside(vault.root, parent):
        raise DomainError("VAULT_PATH_UNSAFE", "transaction path escapes the Vault")
    if target.exists() and not _inside(vault.root, target.resolve(strict=True)):
        raise DomainError("VAULT_PATH_UNSAFE", "transaction target escapes the Vault")
    return target


def _fsync_parent(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_bytes(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_parent(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = _now()
    content = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    _replace_bytes(path, content)


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DomainError("VAULT_RECOVERY_FAILED", "transaction manifest is unreadable") from error
    if not isinstance(value, dict):
        raise DomainError("VAULT_RECOVERY_FAILED", "transaction manifest is not an object")
    manifest = cast(dict[str, Any], value)
    required = {
        "transaction_version",
        "transaction_id",
        "operation",
        "state",
        "created_at",
        "updated_at",
        "entries",
    }
    if set(manifest) != required:
        raise DomainError("VAULT_RECOVERY_FAILED", "transaction manifest fields are invalid")
    if manifest["transaction_version"] != TRANSACTION_VERSION:
        raise DomainError("VAULT_RECOVERY_FAILED", "transaction manifest version is unsupported")
    if not isinstance(manifest["transaction_id"], str) or not TRANSACTION_RE.fullmatch(
        manifest["transaction_id"]
    ):
        raise DomainError("VAULT_RECOVERY_FAILED", "transaction ID is invalid")
    if manifest["state"] not in MANIFEST_STATES or not isinstance(manifest["entries"], list):
        raise DomainError("VAULT_RECOVERY_FAILED", "transaction state is invalid")
    for entry in manifest["entries"]:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "expected_checksum",
            "replacement_checksum",
            "staged_path",
            "backup_path",
            "state",
        }:
            raise DomainError("VAULT_RECOVERY_FAILED", "transaction entry is invalid")
        if entry["state"] not in ENTRY_STATES:
            raise DomainError("VAULT_RECOVERY_FAILED", "transaction entry state is invalid")
        for key in ("path", "staged_path", "backup_path"):
            _relative_path(entry[key])
    return manifest


def _default_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class RecoverableTransactions:
    def __init__(self, *, process_alive: Callable[[int], bool] = _default_process_alive) -> None:
        self._process_alive = process_alive

    def _paths(self, vault: Vault) -> tuple[Path, Path]:
        state = vault.path("state")
        return state / "locks" / "vault-write.lock", state / "transactions"

    def _acquire_lock(self, lock_path: Path, transaction_id: str) -> None:
        record = {
            "transaction_version": TRANSACTION_VERSION,
            "transaction_id": transaction_id,
            "pid": os.getpid(),
            "created_at": _now(),
        }
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise DomainError("VAULT_LOCKED", "another writer owns the Vault lock") from error
        with os.fdopen(descriptor, "wb") as stream:
            stream.write((json.dumps(record) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())

    def _release_lock(self, lock_path: Path, transaction_id: str) -> None:
        try:
            record = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise DomainError("VAULT_RECOVERY_FAILED", "Vault lock is malformed") from error
        if not isinstance(record, dict) or record.get("transaction_id") != transaction_id:
            raise DomainError("VAULT_RECOVERY_FAILED", "Vault lock ownership changed")
        lock_path.unlink()

    def commit(
        self,
        vault: Vault,
        operation: str,
        writes: Sequence[WriteRequest],
        *,
        interrupt: Callable[[str], None] | None = None,
    ) -> tuple[str, ...]:
        if operation not in {"relation-update", "migration"} or not writes:
            raise DomainError("VAULT_INVALID", "transaction operation or entries are invalid")
        callback = interrupt or (lambda _: None)
        transaction_id = f"txn_{new_ulid()}"
        lock_path, transactions_root = self._paths(vault)
        self._acquire_lock(lock_path, transaction_id)
        transaction_root = transactions_root / transaction_id
        manifest_path = transaction_root / "manifest.json"
        try:
            if any(transactions_root.iterdir()):
                raise DomainError(
                    "VAULT_RECOVERY_REQUIRED",
                    "an unfinished transaction must be recovered before writing",
                )
            destinations = [_destination(vault, request.path) for request in writes]
            for destination, request in zip(destinations, writes, strict=True):
                if checksum_file(destination) != request.expected_checksum:
                    raise DomainError(
                        "VAULT_WRITE_CONFLICT", "durable file changed before transaction prepare"
                    )
            (transaction_root / "staged").mkdir(parents=True)
            (transaction_root / "backups").mkdir()
            entries: list[dict[str, Any]] = []
            for index, request in enumerate(writes):
                staged = transaction_root / "staged" / f"{index:04d}"
                backup = transaction_root / "backups" / f"{index:04d}"
                entries.append(
                    {
                        "path": request.path,
                        "expected_checksum": request.expected_checksum,
                        "replacement_checksum": checksum_bytes(request.content),
                        "staged_path": staged.relative_to(vault.root).as_posix(),
                        "backup_path": backup.relative_to(vault.root).as_posix(),
                        "state": "pending",
                    }
                )
            created = _now()
            manifest: dict[str, Any] = {
                "transaction_version": TRANSACTION_VERSION,
                "transaction_id": transaction_id,
                "operation": operation,
                "state": "preparing",
                "created_at": created,
                "updated_at": created,
                "entries": entries,
            }
            _write_manifest(manifest_path, manifest)
            callback("after-preparing")
            for index, request in enumerate(writes):
                staged = vault.root.joinpath(*PurePosixPath(entries[index]["staged_path"]).parts)
                _replace_bytes(staged, request.content)
                callback(f"after-stage-{index}")
            manifest["state"] = "prepared"
            _write_manifest(manifest_path, manifest)
            callback("after-prepared")
            for destination, request in zip(destinations, writes, strict=True):
                if checksum_file(destination) != request.expected_checksum:
                    raise DomainError(
                        "VAULT_WRITE_CONFLICT", "durable file changed before transaction commit"
                    )
            manifest["state"] = "committing"
            _write_manifest(manifest_path, manifest)
            callback("after-committing")
            for index, (destination, entry) in enumerate(zip(destinations, entries, strict=True)):
                callback(f"before-entry-{index}")
                backup = vault.root.joinpath(*PurePosixPath(entry["backup_path"]).parts)
                if destination.exists():
                    shutil.copyfile(destination, backup)
                    with backup.open("ab") as stream:
                        os.fsync(stream.fileno())
                entry["state"] = "backed_up"
                _write_manifest(manifest_path, manifest)
                callback(f"after-backup-{index}")
                staged = vault.root.joinpath(*PurePosixPath(entry["staged_path"]).parts)
                os.replace(staged, destination)
                _fsync_parent(destination)
                callback(f"after-replace-{index}")
                entry["state"] = "replaced"
                _write_manifest(manifest_path, manifest)
                callback(f"after-entry-{index}")
            manifest["state"] = "committed"
            _write_manifest(manifest_path, manifest)
            callback("after-committed")
        except Exception:
            if manifest_path.exists():
                manifest = _load_manifest(manifest_path)
                if manifest["state"] != "committed":
                    self._rollback(vault, transaction_root, manifest)
                    self._cleanup(vault, transaction_root)
            elif transaction_root.exists():
                self._cleanup(vault, transaction_root)
            self._release_lock(lock_path, transaction_id)
            raise
        self._cleanup(vault, transaction_root)
        self._release_lock(lock_path, transaction_id)
        return tuple(checksum_bytes(request.content) for request in writes)

    def _rollback(
        self,
        vault: Vault,
        transaction_root: Path,
        manifest: dict[str, Any],
        *,
        interrupt: Callable[[str], None] | None = None,
    ) -> None:
        callback = interrupt or (lambda _: None)
        manifest_path = transaction_root / "manifest.json"
        manifest["state"] = "rolling_back"
        _write_manifest(manifest_path, manifest)
        callback("after-rolling-back")
        for index, entry in reversed(list(enumerate(manifest["entries"]))):
            destination = _destination(vault, entry["path"])
            backup = vault.root.joinpath(*PurePosixPath(entry["backup_path"]).parts)
            if not _inside(transaction_root, backup.resolve(strict=False)):
                raise DomainError("VAULT_RECOVERY_FAILED", "backup path escapes transaction")
            if entry["state"] in {"backed_up", "replaced"}:
                if backup.exists():
                    os.replace(backup, destination)
                    _fsync_parent(destination)
                elif entry["expected_checksum"] is None:
                    destination.unlink(missing_ok=True)
                elif checksum_file(destination) != entry["expected_checksum"]:
                    raise DomainError("VAULT_RECOVERY_FAILED", "required backup is missing")
                entry["state"] = "restored"
                _write_manifest(manifest_path, manifest)
                callback(f"after-restore-{index}")
        for entry in manifest["entries"]:
            destination = _destination(vault, entry["path"])
            if checksum_file(destination) != entry["expected_checksum"]:
                raise DomainError("VAULT_RECOVERY_FAILED", "rollback checksum verification failed")
        manifest["state"] = "rolled_back"
        _write_manifest(manifest_path, manifest)
        callback("after-rolled-back")

    def _cleanup(self, vault: Vault, transaction_root: Path) -> None:
        _, transactions_root = self._paths(vault)
        resolved_root = transaction_root.resolve(strict=True)
        if resolved_root.parent != transactions_root.resolve(
            strict=True
        ) or not TRANSACTION_RE.fullmatch(resolved_root.name):
            raise DomainError("VAULT_RECOVERY_FAILED", "transaction cleanup target is unsafe")
        shutil.rmtree(resolved_root)

    def recover(self, vault: Vault, *, interrupt: Callable[[str], None] | None = None) -> str:
        lock_path, transactions_root = self._paths(vault)
        transaction_dirs = sorted(path for path in transactions_root.iterdir() if path.is_dir())
        unexplained = [path for path in transactions_root.iterdir() if not path.is_dir()]
        if unexplained or len(transaction_dirs) != 1:
            if not transaction_dirs and not unexplained:
                return "clean"
            raise DomainError("VAULT_RECOVERY_FAILED", "transaction state is ambiguous")
        transaction_root = transaction_dirs[0]
        manifest = _load_manifest(transaction_root / "manifest.json")
        transaction_id = manifest["transaction_id"]
        if transaction_root.name != transaction_id:
            raise DomainError(
                "VAULT_RECOVERY_FAILED", "transaction directory does not match manifest"
            )
        if lock_path.exists():
            try:
                record = json.loads(lock_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise DomainError("VAULT_RECOVERY_FAILED", "Vault lock is malformed") from error
            if not isinstance(record, dict) or record.get("transaction_id") != transaction_id:
                raise DomainError("VAULT_RECOVERY_FAILED", "Vault lock does not own transaction")
            pid = record.get("pid")
            if not isinstance(pid, int):
                raise DomainError("VAULT_RECOVERY_FAILED", "Vault lock PID is invalid")
            if self._process_alive(pid):
                raise DomainError("VAULT_LOCKED", "transaction owner is still active")
            lock_path.unlink()
        recovery_id = transaction_id
        self._acquire_lock(lock_path, recovery_id)
        try:
            if manifest["state"] == "committed":
                for entry in manifest["entries"]:
                    if (
                        checksum_file(_destination(vault, entry["path"]))
                        != entry["replacement_checksum"]
                    ):
                        raise DomainError(
                            "VAULT_RECOVERY_FAILED", "committed checksum verification failed"
                        )
                outcome = "committed"
            elif manifest["state"] == "rolled_back":
                for entry in manifest["entries"]:
                    if (
                        checksum_file(_destination(vault, entry["path"]))
                        != entry["expected_checksum"]
                    ):
                        raise DomainError(
                            "VAULT_RECOVERY_FAILED", "rollback checksum verification failed"
                        )
                outcome = "rolled-back"
            else:
                self._rollback(vault, transaction_root, manifest, interrupt=interrupt)
                outcome = "rolled-back"
            self._cleanup(vault, transaction_root)
        except Exception:
            self._release_lock(lock_path, recovery_id)
            raise
        self._release_lock(lock_path, recovery_id)
        return outcome
