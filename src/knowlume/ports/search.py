from __future__ import annotations

from typing import Protocol

from knowlume.domain.search import ContextScope, SearchFilters, SearchHit
from knowlume.ports.vault import Vault


class ProjectionStore(Protocol):
    def status(self, vault: Vault) -> dict[str, object]: ...

    def build(self, vault: Vault, *, rebuild: bool = False) -> dict[str, object]: ...

    def refresh_if_present(self, vault: Vault) -> bool: ...


class SearchBackend(Protocol):
    def search(
        self,
        vault: Vault,
        query: str,
        filters: SearchFilters,
        scope: ContextScope,
        limit: int,
    ) -> tuple[SearchHit, ...]: ...
