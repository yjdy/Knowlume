from __future__ import annotations

from pathlib import Path
from typing import Protocol

from knowlume.domain.config import VaultConfig


class VaultStoragePort(Protocol):
    def normalize_path(self, value: str | Path, *, base: Path) -> Path: ...

    def find_nearest_vault(self, start: Path) -> Path | None: ...

    def default_vault(self) -> Path: ...

    def has_marker(self, root: Path) -> bool: ...

    def load_config(self, root: Path) -> VaultConfig: ...

    def initialize(self, root: Path, config_text: str, config: VaultConfig) -> bool: ...
