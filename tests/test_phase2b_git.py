from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from knowlume.adapters.git_remote import GitRemoteResolver
from knowlume.domain.capture import RepositoryInput, normalize_repository_url
from knowlume.domain.values import DomainError
from knowlume.ports.git import GitCommandResult


@dataclass
class Runner:
    result: GitCommandResult | None = None
    error: Exception | None = None
    calls: list[tuple[tuple[str, ...], dict[str, str], Path, float]] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str],
        cwd: Path,
        timeout: float,
    ) -> GitCommandResult:
        self.calls.append((tuple(argv), dict(environment), cwd, timeout))
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def _repository() -> RepositoryInput:
    return normalize_repository_url("https://github.com/OpenAI/openai-python.git/", configured=True)


@pytest.mark.parametrize("commit", ["a" * 40, "b" * 64])
def test_git_remote_resolution_is_narrow_anonymous_and_isolated(commit: str) -> None:
    runner = Runner(GitCommandResult(0, f"ref: refs/heads/main\tHEAD\n{commit}\tHEAD\n".encode()))
    result = GitRemoteResolver(
        runner=runner, environment={"PATH": "safe", "GIT_CONFIG_GLOBAL": "unsafe"}
    ).resolve(_repository())
    assert result.default_branch == "main" and result.commit == commit
    assert result.canonical_identity == f"repo:github.com/OpenAI/openai-python@{commit}"
    argv, environment, cwd, timeout = runner.calls[0]
    assert argv == ("git", "ls-remote", "--symref", result.canonical_url, "HEAD")
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GCM_INTERACTIVE"] == "never"
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] != "unsafe"
    assert environment["GIT_CONFIG_COUNT"] == "2"
    assert environment["GIT_CONFIG_KEY_0"] == "credential.helper"
    assert environment["GIT_CONFIG_VALUE_0"] == ""
    assert environment["GIT_ASKPASS"] == environment["SSH_ASKPASS"]
    assert cwd.is_absolute() and timeout > 0
    assert not any(
        operation in argv for operation in ("clone", "fetch", "checkout", "show", "cat-file")
    )


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (GitCommandResult(1, b"secret remote failure"), "GIT_REMOTE_UNAVAILABLE"),
        (GitCommandResult(0, b"malformed"), "GIT_REMOTE_INVALID"),
        (
            GitCommandResult(0, f"ref: refs/heads/main\tHEAD\n{'A' * 40}\tHEAD\n".encode()),
            "GIT_REMOTE_INVALID",
        ),
        (
            GitCommandResult(0, f"ref: refs/tags/v1\tHEAD\n{'a' * 40}\tHEAD\n".encode()),
            "GIT_REMOTE_INVALID",
        ),
        (GitCommandResult(0, f"{'a' * 40}\tHEAD\n".encode()), "GIT_REMOTE_INVALID"),
        (GitCommandResult(0, b"ref: refs/heads/main\tHEAD\n"), "GIT_REMOTE_INVALID"),
        (
            GitCommandResult(
                0,
                f"ref: refs/heads/main\tHEAD\n{'a' * 12}\tHEAD\n".encode(),
            ),
            "GIT_REMOTE_INVALID",
        ),
        (
            GitCommandResult(
                0,
                f"ref: refs/heads/../main\tHEAD\n{'a' * 40}\tHEAD\n".encode(),
            ),
            "GIT_REMOTE_INVALID",
        ),
        (
            GitCommandResult(
                0,
                (
                    "ref: refs/heads/main\tHEAD\n"
                    "ref: refs/heads/other\tHEAD\n"
                    f"{'a' * 40}\tHEAD\n"
                ).encode(),
            ),
            "GIT_REMOTE_INVALID",
        ),
    ],
)
def test_git_failures_are_typed_and_redacted(result: GitCommandResult, code: str) -> None:
    runner = Runner(result)
    with pytest.raises(DomainError) as caught:
        GitRemoteResolver(runner=runner, environment={}).resolve(_repository())
    assert caught.value.code == code
    assert "secret" not in str(caught.value)
    assert str(runner.calls[0][2]) not in str(caught.value)


def test_missing_git_is_a_typed_capability_failure() -> None:
    runner = Runner(error=FileNotFoundError("git with secret path"))
    with pytest.raises(DomainError) as caught:
        GitRemoteResolver(runner=runner, environment={}).resolve(_repository())
    assert caught.value.code == "GIT_CAPABILITY_UNAVAILABLE"
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired("git containing secret", 1),
        OSError("secret operating-system detail"),
    ],
)
def test_timeout_and_runner_failures_are_unavailable_and_redacted(error: Exception) -> None:
    runner = Runner(error=error)
    with pytest.raises(DomainError) as caught:
        GitRemoteResolver(runner=runner, environment={}).resolve(_repository())
    assert caught.value.code == "GIT_REMOTE_UNAVAILABLE"
    assert "secret" not in str(caught.value)


def test_authentication_required_is_a_redacted_unavailable_failure() -> None:
    runner = Runner(GitCommandResult(128, b"fatal: password for secret-user is required"))
    with pytest.raises(DomainError) as caught:
        GitRemoteResolver(runner=runner, environment={}).resolve(_repository())
    assert caught.value.code == "GIT_REMOTE_UNAVAILABLE"
    assert "secret-user" not in str(caught.value)
