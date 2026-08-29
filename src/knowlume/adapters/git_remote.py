from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from knowlume.domain.capture import RepositoryInput
from knowlume.domain.values import DomainError
from knowlume.ports.git import GitCommandResult, GitCommandRunner, RepositoryMetadata


class SubprocessGitRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        timeout: float,
    ) -> GitCommandResult:
        command = list(argv)
        if os.name == "nt":
            executable = shutil.which(command[0], path=environment.get("PATH"))
            if executable is None:
                raise FileNotFoundError(command[0])
            command[0] = executable
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=dict(environment),
            check=False,
            capture_output=True,
            timeout=timeout,
        )
        return GitCommandResult(completed.returncode, completed.stdout)


def _parse_remote_head(stdout: bytes) -> tuple[str, str]:
    try:
        lines = stdout.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise DomainError("GIT_REMOTE_INVALID", "remote HEAD response is malformed") from error
    symbolic: list[str] = []
    commits: list[str] = []
    for line in lines:
        if line.startswith("ref: "):
            parts = line.split("\t")
            if len(parts) == 2 and parts[1] == "HEAD":
                symbolic.append(parts[0].removeprefix("ref: "))
            else:
                raise DomainError("GIT_REMOTE_INVALID", "remote HEAD response is malformed")
        else:
            parts = line.split("\t")
            if len(parts) == 2 and parts[1] == "HEAD":
                commits.append(parts[0])
            else:
                raise DomainError("GIT_REMOTE_INVALID", "remote HEAD response is malformed")
    if len(symbolic) != 1 or len(commits) != 1 or not symbolic[0].startswith("refs/heads/"):
        raise DomainError("GIT_REMOTE_INVALID", "remote HEAD response is malformed")
    branch = symbolic[0].removeprefix("refs/heads/")
    commit = commits[0]
    components = branch.split("/")
    invalid_branch = (
        not branch
        or branch == "@"
        or branch.endswith((".", "/", ".lock"))
        or ".." in branch
        or "//" in branch
        or "@{" in branch
        or any(not component or component.startswith(".") for component in components)
        or re.search(r"[\x00-\x20~^:?*\[\\]", branch) is not None
    )
    if invalid_branch or not (
        len(commit) in {40, 64}
        and all(character in "0123456789abcdef" for character in commit)
    ):
        raise DomainError("GIT_REMOTE_INVALID", "remote HEAD response is malformed")
    return branch, commit


class GitRemoteResolver:
    def __init__(
        self,
        *,
        runner: GitCommandRunner | None = None,
        environment: Mapping[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._runner = runner or SubprocessGitRunner()
        self._environment = os.environ if environment is None else environment
        self._timeout = timeout

    def resolve(self, repository: RepositoryInput) -> RepositoryMetadata:
        with tempfile.TemporaryDirectory(prefix="knowlume-git-") as temporary_name:
            temporary = Path(temporary_name).resolve()
            global_config = temporary / "global.gitconfig"
            global_config.write_bytes(b"")
            if os.name == "nt":
                askpass = temporary / "reject-askpass.cmd"
                askpass.write_text("@exit /b 1\n", encoding="ascii")
            else:
                askpass = temporary / "reject-askpass.sh"
                askpass.write_text("#!/bin/sh\nexit 1\n", encoding="ascii")
                askpass.chmod(0o700)
            environment = {
                key: value
                for key, value in self._environment.items()
                if not key.upper().startswith(("GIT_", "GCM_"))
                and key.upper() != "SSH_ASKPASS"
            }
            environment.update(
                {
                    "GIT_TERMINAL_PROMPT": "0",
                    "GCM_INTERACTIVE": "never",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": str(global_config),
                    "GIT_ASKPASS": str(askpass),
                    "SSH_ASKPASS": str(askpass),
                    "GIT_CONFIG_COUNT": "2",
                    "GIT_CONFIG_KEY_0": "credential.helper",
                    "GIT_CONFIG_VALUE_0": "",
                    "GIT_CONFIG_KEY_1": "credential.interactive",
                    "GIT_CONFIG_VALUE_1": "false",
                }
            )
            argv = ("git", "ls-remote", "--symref", repository.canonical_url, "HEAD")
            try:
                result = self._runner.run(
                    argv,
                    environment=environment,
                    cwd=temporary,
                    timeout=self._timeout,
                )
            except FileNotFoundError as error:
                raise DomainError(
                    "GIT_CAPABILITY_UNAVAILABLE", "Git executable is unavailable"
                ) from error
            except subprocess.TimeoutExpired as error:
                raise DomainError(
                    "GIT_REMOTE_UNAVAILABLE", "anonymous remote HEAD resolution is unavailable"
                ) from error
            except OSError as error:
                raise DomainError(
                    "GIT_REMOTE_UNAVAILABLE", "anonymous remote HEAD resolution is unavailable"
                ) from error
            if result.returncode != 0:
                raise DomainError(
                    "GIT_REMOTE_UNAVAILABLE", "anonymous remote HEAD resolution is unavailable"
                )
            branch, commit = _parse_remote_head(result.stdout)
        return RepositoryMetadata(
            title=repository.project_path.rsplit("/", 1)[-1],
            canonical_url=repository.canonical_url,
            host=repository.host,
            project_path=repository.project_path,
            default_branch=branch,
            commit=commit,
        )
