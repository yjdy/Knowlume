from __future__ import annotations

from typing import Literal, Protocol

type ProbeName = Literal["vault", "sqlite", "git", "zotero"]


class DiagnosticProbePort(Protocol):
    """Run only the named read-only probe; return on health, raise on failure.

    Construction must not perform I/O. Implementations preserve files, discover a Vault
    only for vault/sqlite, and contact a supported loopback API only for zotero.
    The application sanitizes and aggregates exceptions from each selected call.
    """

    def probe(self, name: ProbeName) -> None: ...
