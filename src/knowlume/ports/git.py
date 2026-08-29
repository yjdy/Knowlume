from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from knowlume.domain.capture import RepositoryInput


@dataclass(frozen=True)
class GitCommandResult:
    returncode: int
    stdout: bytes


class GitCommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        timeout: float,
    ) -> GitCommandResult: ...


@dataclass(frozen=True)
class RepositoryMetadata:
    title: str
    canonical_url: str
    host: str
    project_path: str
    default_branch: str
    commit: str

    @property
    def canonical_identity(self) -> str:
        return f"repo:{self.host}/{self.project_path}@{self.commit}"


class RepositoryMetadataPort(Protocol):
    def resolve(self, repository: RepositoryInput) -> RepositoryMetadata: ...
