from __future__ import annotations

from pathlib import Path

from knowlume.ports.vault import Vault, VaultPort


class VaultService:
    def __init__(self, port: VaultPort) -> None:
        self._port = port

    def initialize(self, target: Path, config_text: str) -> Vault:
        return self._port.initialize(target, config_text)

    def discover(self, *, explicit: Path | None = None, cwd: Path | None = None) -> Vault:
        return self._port.discover(explicit=explicit, cwd=cwd or Path.cwd())
