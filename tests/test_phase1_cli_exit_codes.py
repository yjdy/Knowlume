from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from knowlume.cli import app
from knowlume.domain.values import DomainError

runner = CliRunner()


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("FIELD_INVALID", 3),
        ("VAULT_WRITE_CONFLICT", 4),
        ("CHANGED_FILES_UNAVAILABLE", 5),
        ("VAULT_PATH_UNSAFE", 6),
    ],
)
def test_typed_phase1_errors_use_frozen_exit_codes(
    monkeypatch: pytest.MonkeyPatch, code: str, expected: int
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise DomainError(code, "injected diagnostic")

    monkeypatch.setattr("knowlume.application.vault.VaultService.discover", fail)
    result = runner.invoke(app, ["--vault", "unused", "scan"])
    assert result.exit_code == expected
    assert result.stdout == ""
    assert f"{code}: injected diagnostic" in result.stderr


def test_success_usage_and_unexpected_failure_cover_exit_codes_zero_to_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert runner.invoke(app, ["--help"]).exit_code == 0
    usage = runner.invoke(app, ["init"])
    assert usage.exit_code == 2
    assert usage.stdout == ""

    def unexpected(*args: object, **kwargs: object) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr("knowlume.application.vault.VaultService.discover", unexpected)
    failed = runner.invoke(app, ["--vault", str(tmp_path), "scan"])
    assert failed.exit_code == 1
    assert isinstance(failed.exception, RuntimeError)
