from __future__ import annotations

import hashlib
import os
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from platformdirs import user_data_dir

from knowlume.constants import CONFIGURATION_VERSION, OBJECT_CONTRACT_VERSION
from knowlume.domain.values import DomainError
from knowlume.ports.vault import Vault, VaultConfig

CONFIG_NAME = "knowlume.toml"
CONFIG_KEYS = {
    "sources",
    "notes",
    "snippets",
    "ai_artifacts",
    "relations",
    "state",
}
STANDARD_DIRS = (
    "sources/papers",
    "sources/web",
    "sources/books",
    "sources/oss",
    "notes/ideas",
    "notes/literature",
    "notes/concepts",
    "notes/syntheses",
    "snippets",
    "ai/artifacts",
    "relations",
    ".knowlume/locks",
    ".knowlume/transactions",
)


def checksum_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def checksum_file(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise DomainError("VAULT_INVALID", "durable target is not a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DomainError("VAULT_INVALID", f"{name} must be a table")
    return value


def parse_vault_config(text: str) -> VaultConfig:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise DomainError("VAULT_INVALID", "knowlume.toml is invalid TOML") from error
    if set(data) != {"config_version", "object_contract_version", "vault"}:
        raise DomainError("VAULT_INVALID", "knowlume.toml has missing or unknown fields")
    if data["config_version"] != CONFIGURATION_VERSION:
        raise DomainError("VAULT_VERSION_UNSUPPORTED", "unsupported Vault configuration version")
    if data["object_contract_version"] != OBJECT_CONTRACT_VERSION:
        raise DomainError("VAULT_VERSION_UNSUPPORTED", "unsupported object Contract version")
    paths = _mapping(data["vault"], "vault")
    if set(paths) != CONFIG_KEYS:
        raise DomainError("VAULT_INVALID", "vault table has missing or unknown paths")
    values: dict[str, str] = {}
    for name in sorted(CONFIG_KEYS):
        value = paths[name]
        if not isinstance(value, str) or not value or "\\" in value:
            raise DomainError("VAULT_INVALID", f"vault.{name} is not a portable path")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
            raise DomainError("VAULT_INVALID", f"vault.{name} is not a portable path")
        values[name] = value
    pure_paths = {name: PurePosixPath(value) for name, value in values.items()}
    for left_name, left in pure_paths.items():
        for right_name, right in pure_paths.items():
            if left_name >= right_name:
                continue
            if left == right or left in right.parents or right in left.parents:
                raise DomainError("VAULT_PATH_CONFLICT", "configured Vault roots overlap")
    return VaultConfig(CONFIGURATION_VERSION, OBJECT_CONTRACT_VERSION, **values)


def _inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_existing_root(path: Path) -> Path:
    try:
        root = path.resolve(strict=True)
    except OSError as error:
        raise DomainError("VAULT_NOT_FOUND", "selected Vault does not exist") from error
    if not root.is_dir():
        raise DomainError("VAULT_INVALID", "selected Vault is not a directory")
    return root


def load_vault(path: Path) -> Vault:
    root = _safe_existing_root(path)
    marker = root / CONFIG_NAME
    if not marker.is_file():
        raise DomainError("VAULT_NOT_FOUND", "selected directory has no knowlume.toml")
    try:
        config = parse_vault_config(marker.read_text(encoding="utf-8"))
    except OSError as error:
        raise DomainError("VAULT_INVALID", "knowlume.toml cannot be read") from error
    for name in CONFIG_KEYS:
        configured = root / getattr(config, name)
        try:
            resolved = configured.resolve(strict=True)
        except OSError as error:
            raise DomainError("VAULT_INVALID", f"configured {name} directory is missing") from error
        if not resolved.is_dir():
            raise DomainError("VAULT_INVALID", f"configured {name} path is not a directory")
        if not _inside(root, resolved):
            raise DomainError("VAULT_PATH_UNSAFE", f"configured {name} path escapes the Vault")
    return Vault(root, config)


class FilesystemVault:
    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        default_root: Path | None = None,
    ) -> None:
        self._environment = os.environ if environment is None else environment
        self._default_root = default_root

    def discover(self, *, explicit: Path | None, cwd: Path) -> Vault:
        if explicit is not None:
            return load_vault(explicit)
        if value := self._environment.get("KNOWLUME_VAULT"):
            candidates = [item for item in value.split(os.pathsep) if item]
            if not candidates:
                raise DomainError("VAULT_INVALID", "KNOWLUME_VAULT contains no usable path")
            if len(candidates) > 1:
                roots = {str(Path(item).resolve(strict=False)) for item in candidates}
                if len(roots) > 1:
                    raise DomainError(
                        "VAULT_AMBIGUOUS",
                        "KNOWLUME_VAULT selects more than one Vault",
                    )
            return load_vault(Path(candidates[0]))
        current = cwd.resolve(strict=True)
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            if (candidate / CONFIG_NAME).is_file():
                return load_vault(candidate)
        default = self._default_root or Path(user_data_dir("knowlume")) / "vault"
        if (default / CONFIG_NAME).is_file():
            return load_vault(default)
        raise DomainError("VAULT_NOT_FOUND", "no Knowlume Vault could be discovered")

    def initialize(self, target: Path, config_text: str) -> Vault:
        config = parse_vault_config(config_text)
        if target.exists():
            root = target.resolve(strict=True)
            if not root.is_dir():
                raise DomainError("VAULT_INVALID", "initialization target is not a directory")
            entries = list(root.iterdir())
            if entries:
                if (root / CONFIG_NAME).is_file():
                    return load_vault(root)
                raise DomainError("VAULT_INVALID", "initialization target is not empty")
            created_root = False
        else:
            parent = target.parent.resolve(strict=True)
            root = parent / target.name
            created_root = True
        created: list[Path] = []
        try:
            if created_root:
                root.mkdir()
                created.append(root)
            for relative in STANDARD_DIRS:
                directory = root.joinpath(*PurePosixPath(relative).parts)
                if not _inside(root, directory.resolve(strict=False)):
                    raise DomainError("VAULT_PATH_UNSAFE", "initialization path escapes the Vault")
                missing: list[Path] = []
                cursor = directory
                while cursor != root and not cursor.exists():
                    missing.append(cursor)
                    cursor = cursor.parent
                directory.mkdir(parents=True, exist_ok=True)
                created.extend(reversed(missing))
            self._atomic_path(root, root / CONFIG_NAME, config_text.encode("utf-8"), None)
            return Vault(root.resolve(strict=True), config)
        except Exception:
            for path in reversed(created):
                try:
                    path.rmdir()
                except OSError:
                    pass
            raise

    def atomic_write(
        self, vault: Vault, relative_path: str, content: bytes, expected_checksum: str | None
    ) -> str:
        state_root = vault.path("state")
        if (state_root / "locks" / "vault-write.lock").exists():
            raise DomainError("VAULT_LOCKED", "another writer owns the Vault lock")
        transactions = state_root / "transactions"
        if any(transactions.iterdir()):
            raise DomainError(
                "VAULT_RECOVERY_REQUIRED",
                "an unfinished transaction must be recovered before writing",
            )
        relative = PurePosixPath(relative_path)
        if (
            "\\" in relative_path
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != relative_path
        ):
            raise DomainError("VAULT_PATH_UNSAFE", "write path is not Vault-relative")
        destination = vault.root.joinpath(*relative.parts)
        return self._atomic_path(vault.root, destination, content, expected_checksum)

    def _atomic_path(
        self, root: Path, destination: Path, content: bytes, expected_checksum: str | None
    ) -> str:
        root = root.resolve(strict=True)
        parent = destination.parent.resolve(strict=True)
        if not _inside(root, parent):
            raise DomainError("VAULT_PATH_UNSAFE", "write target escapes the Vault")
        if destination.exists() and not _inside(root, destination.resolve(strict=True)):
            raise DomainError("VAULT_PATH_UNSAFE", "write target escapes the Vault")
        if checksum_file(destination) != expected_checksum:
            raise DomainError("VAULT_WRITE_CONFLICT", "durable file changed after it was read")
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            if os.name != "nt":
                directory_fd = os.open(parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)
        return checksum_bytes(content)
