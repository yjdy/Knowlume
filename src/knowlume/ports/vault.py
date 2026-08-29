from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast


@dataclass(frozen=True)
class VaultConfig:
    config_version: int
    object_contract_version: int
    sources: str
    notes: str
    snippets: str
    ai_artifacts: str
    relations: str
    state: str
    repository_hosts: tuple[str, ...] = ("github.com", "gitlab.com")


@dataclass(frozen=True)
class Vault:
    root: Path
    config: VaultConfig

    def path(self, name: str) -> Path:
        return self.root / cast(str, getattr(self.config, name))


class VaultPort(Protocol):
    def initialize(self, target: Path, config_text: str) -> Vault: ...

    def discover(self, *, explicit: Path | None, cwd: Path) -> Vault: ...

    def atomic_write(
        self, vault: Vault, relative_path: str, content: bytes, expected_checksum: str | None
    ) -> str: ...

    def atomic_delete(self, vault: Vault, relative_path: str, expected_checksum: str) -> None: ...
