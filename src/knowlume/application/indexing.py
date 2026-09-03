from __future__ import annotations

from knowlume.ports.search import ProjectionStore
from knowlume.ports.vault import Vault


class IndexRefreshService:
    """Best-effort application coupling after a durable mutation has committed."""

    def __init__(self, store: ProjectionStore) -> None:
        self._store = store

    def after_mutation(self, vault: Vault, *, changed: bool = True) -> tuple[str, ...]:
        if not changed:
            return ()
        try:
            self._store.refresh_if_present(vault)
        except Exception:
            return ("INDEX_REFRESH_FAILED",)
        return ()
