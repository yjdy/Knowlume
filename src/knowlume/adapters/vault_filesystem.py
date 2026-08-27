from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from platformdirs import PlatformDirs

from knowlume.domain.config import VaultConfig, parse_vault_config
from knowlume.domain.values import DomainError

FaultHook = Callable[[str, Path], None]


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def file_checksum(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise DomainError("VAULT_PATH_UNSAFE", "write target is not a regular file")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except PermissionError as error:
        raise DomainError("VAULT_UNAVAILABLE", "write target is not readable") from error
    return f"sha256:{digest.hexdigest()}"


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _existing_components(path: Path) -> list[Path]:
    absolute = path.absolute()
    components: list[Path] = []
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.exists() or current.is_symlink():
            components.append(current)
    return components


def _reject_reparse(path: Path) -> None:
    if any(_is_reparse(component) for component in _existing_components(path)):
        raise DomainError("VAULT_PATH_UNSAFE", "path crosses a symlink or junction")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AtomicFileWriter:
    def __init__(self, vault_root: Path, *, fault_hook: FaultHook | None = None) -> None:
        self._root = vault_root.resolve(strict=True)
        self._fault_hook = fault_hook

    def _target(self, target: Path) -> tuple[Path, Path]:
        absolute = target if target.is_absolute() else self._root / target
        _reject_reparse(absolute)
        try:
            parent = absolute.parent.resolve(strict=True)
            parent.relative_to(self._root)
        except (FileNotFoundError, ValueError) as error:
            raise DomainError("VAULT_PATH_UNSAFE", "write target escapes the vault") from error
        normalized = parent / absolute.name
        if normalized == self._root / "knowlume.toml":
            relative = Path("knowlume.toml")
        else:
            relative = normalized.relative_to(self._root)
        return normalized, relative

    def write_bytes(
        self,
        target: Path,
        content: bytes,
        *,
        expected_checksum: str | None,
    ) -> str:
        normalized, relative = self._target(target)
        lock_root = self._root / ".knowlume" / "locks"
        try:
            lock_root.mkdir(parents=True, exist_ok=True)
        except PermissionError as error:
            raise DomainError("VAULT_UNAVAILABLE", "vault lock directory is not writable") from error
        lock_name = hashlib.sha256(relative.as_posix().encode()).hexdigest()
        lock_path = lock_root / f"file-{lock_name}.lock"
        owner = str(uuid.uuid4()).encode("ascii")
        lock_descriptor: int | None = None
        temporary_path: Path | None = None
        try:
            try:
                lock_descriptor = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError as error:
                raise DomainError("WRITE_CONFLICT", "another writer owns the target") from error
            os.write(lock_descriptor, owner)
            os.fsync(lock_descriptor)
            os.close(lock_descriptor)
            lock_descriptor = None

            if file_checksum(normalized) != expected_checksum:
                raise DomainError("WRITE_CONFLICT", "target changed from the expected state")
            descriptor, temporary_name = tempfile.mkstemp(
                dir=normalized.parent,
                prefix=f".{normalized.name}.",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if self._fault_hook is not None:
                self._fault_hook("before_replace", normalized)
            if file_checksum(normalized) != expected_checksum:
                raise DomainError("WRITE_CONFLICT", "target changed before atomic replacement")
            os.replace(temporary_path, normalized)
            temporary_path = None
            _fsync_directory(normalized.parent)
            return sha256_bytes(content)
        except PermissionError as error:
            raise DomainError("VAULT_UNAVAILABLE", "vault target is not writable") from error
        finally:
            if lock_descriptor is not None:
                os.close(lock_descriptor)
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
            try:
                if lock_path.read_bytes() == owner:
                    lock_path.unlink()
            except FileNotFoundError:
                pass

    def write_text(
        self,
        target: Path,
        text: str,
        *,
        expected_checksum: str | None,
    ) -> str:
        return self.write_bytes(target, text.encode("utf-8"), expected_checksum=expected_checksum)


class FilesystemVaultStorage:
    def normalize_path(self, value: str | Path, *, base: Path) -> Path:
        raw = Path(value)
        if not str(raw) or ".." in raw.parts:
            raise DomainError("VAULT_PATH_UNSAFE", "vault path contains traversal")
        absolute = raw if raw.is_absolute() else base / raw
        absolute = absolute.absolute()
        _reject_reparse(absolute)
        return absolute

    def find_nearest_vault(self, start: Path) -> Path | None:
        current = self.normalize_path(start, base=Path.cwd())
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            if self.has_marker(candidate):
                return candidate
        return None

    def default_vault(self) -> Path:
        return Path(PlatformDirs("knowlume", appauthor=False).user_data_path) / "vault"

    def has_marker(self, root: Path) -> bool:
        marker = root / "knowlume.toml"
        return marker.is_file() and not _is_reparse(marker)

    def _validate_layout(self, root: Path, config: VaultConfig) -> None:
        resolved_root = root.resolve(strict=True)
        for configured in config.paths.values():
            relative = Path(*PurePosixPath(configured).parts)
            candidate = root / relative
            _reject_reparse(candidate)
            existing_parent = candidate
            while not existing_parent.exists() and existing_parent != root:
                existing_parent = existing_parent.parent
            try:
                existing_parent.resolve(strict=True).relative_to(resolved_root)
            except (FileNotFoundError, ValueError) as error:
                raise DomainError("VAULT_PATH_UNSAFE", "configured path escapes the vault") from error

    def load_config(self, root: Path) -> VaultConfig:
        _reject_reparse(root)
        marker = root / "knowlume.toml"
        if not marker.is_file() or _is_reparse(marker):
            raise DomainError("VAULT_NOT_FOUND", "selected vault has no regular knowlume.toml")
        try:
            text = marker.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise DomainError("VAULT_UNAVAILABLE", "vault configuration is unavailable") from error
        config = parse_vault_config(text)
        self._validate_layout(root, config)
        return config

    @staticmethod
    def _mkdir(path: Path, created: list[Path]) -> None:
        missing: list[Path] = []
        current = path
        while not current.exists():
            missing.append(current)
            if current.parent == current:
                break
            current = current.parent
        for directory in reversed(missing):
            directory.mkdir()
            created.append(directory)

    @staticmethod
    def _rollback_directories(created: list[Path]) -> None:
        for directory in reversed(created):
            try:
                directory.rmdir()
            except (FileNotFoundError, OSError):
                pass

    def initialize(self, root: Path, config_text: str, config: VaultConfig) -> bool:
        _reject_reparse(root)
        if root.exists() and not root.is_dir():
            raise DomainError("VAULT_TARGET_NOT_EMPTY", "initialization target is not a directory")
        if root.exists() and self.has_marker(root):
            self.load_config(root)
            return False
        if root.exists():
            try:
                if next(root.iterdir(), None) is not None:
                    raise DomainError("VAULT_TARGET_NOT_EMPTY", "initialization target is not empty")
            except PermissionError as error:
                raise DomainError("VAULT_UNAVAILABLE", "initialization target is unavailable") from error

        created: list[Path] = []
        try:
            self._mkdir(root, created)
            self._validate_layout(root, config)
            sources = root / Path(*config.paths.sources.parts)
            notes = root / Path(*config.paths.notes.parts)
            paths = [
                *(sources / name for name in ("papers", "web", "books", "oss")),
                *(notes / name for name in ("ideas", "literature", "concepts", "syntheses")),
                root / Path(*config.paths.snippets.parts),
                root / Path(*config.paths.ai_artifacts.parts),
                root / Path(*config.paths.relations.parts),
                root / ".knowlume" / "locks",
                root / ".knowlume" / "transactions",
            ]
            for path in paths:
                self._mkdir(path, created)
            writer = AtomicFileWriter(root)
            writer.write_text(root / "knowlume.toml", config_text, expected_checksum=None)
        except DomainError:
            self._rollback_directories(created)
            raise
        except PermissionError as error:
            self._rollback_directories(created)
            raise DomainError("VAULT_UNAVAILABLE", "initialization target is not writable") from error
        except OSError as error:
            self._rollback_directories(created)
            raise DomainError("VAULT_UNAVAILABLE", "vault initialization failed") from error
        return True
