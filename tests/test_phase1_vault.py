from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from knowlume.adapters.vault_filesystem import (
    AtomicFileWriter,
    FilesystemVaultStorage,
    file_checksum,
    sha256_bytes,
)
from knowlume.application.errors import ApplicationError
from knowlume.application.vaults import initialize_vault, resolve_vault
from knowlume.cli import app
from knowlume.domain.config import parse_vault_config
from knowlume.domain.values import DomainError
from phase0_support import ROOT

CONFIG_TEMPLATE = (ROOT / "templates" / "config" / "v1" / "knowlume.toml").read_text(
    encoding="utf-8"
)
VAULT_ID = "vault_01JSTAG7N9Q3V5X8Y2Z4A6B8D9"


def _initialize(path: Path, *, storage: FilesystemVaultStorage | None = None) -> None:
    result = initialize_vault(
        path,
        global_vault_values=(),
        cwd=path.parent,
        config_template=CONFIG_TEMPLATE,
        storage=storage or FilesystemVaultStorage(),
        vault_id_factory=lambda: VAULT_ID,
    )
    assert result.created is True


def test_init_creates_portable_topology_and_is_idempotent(tmp_path: Path) -> None:
    vault = tmp_path / "Vault with 空格"
    storage = FilesystemVaultStorage()
    result = initialize_vault(
        vault,
        global_vault_values=(str(vault), str(vault / ".")),
        cwd=tmp_path,
        config_template=CONFIG_TEMPLATE,
        storage=storage,
        vault_id_factory=lambda: VAULT_ID,
    )
    assert result.created is True
    assert result.vault_id == VAULT_ID
    expected = {
        "sources/papers",
        "sources/web",
        "sources/books",
        "sources/oss",
        "notes/ideas",
        "notes/literature",
        "notes/concepts",
        "notes/syntheses",
        "snippets",
        "ai/artifacts",
        "relations",
        ".knowlume/locks",
        ".knowlume/transactions",
    }
    assert all((vault / Path(item)).is_dir() for item in expected)
    config_text = (vault / "knowlume.toml").read_text(encoding="utf-8")
    assert str(tmp_path) not in config_text
    assert parse_vault_config(config_text).vault_id == VAULT_ID

    repeated = initialize_vault(
        vault,
        global_vault_values=(),
        cwd=tmp_path,
        config_template=CONFIG_TEMPLATE,
        storage=storage,
        vault_id_factory=lambda: "vault_01JSTAG7N9Q3V5X8Y2Z4A6B8DA",
    )
    assert repeated.created is False
    assert repeated.vault_id == VAULT_ID


def test_init_supports_a_long_nested_path(tmp_path: Path) -> None:
    vault = tmp_path / ("a" * 70) / ("界" * 70) / ("b" * 70)
    _initialize(vault)
    assert (vault / "knowlume.toml").is_file()


def test_init_rejects_non_empty_target_without_removing_user_content(tmp_path: Path) -> None:
    vault = tmp_path / "existing"
    vault.mkdir()
    user_file = vault / "keep.txt"
    user_file.write_text("keep", encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        initialize_vault(
            vault,
            global_vault_values=(),
            cwd=tmp_path,
            config_template=CONFIG_TEMPLATE,
            storage=FilesystemVaultStorage(),
            vault_id_factory=lambda: VAULT_ID,
        )
    assert error.value.code == "VAULT_TARGET_NOT_EMPTY"
    assert user_file.read_text(encoding="utf-8") == "keep"


def test_init_reports_unavailable_directory_and_rolls_back(tmp_path: Path) -> None:
    vault = tmp_path / "read-only"
    storage = FilesystemVaultStorage()

    def fail_mkdir(path: Path, created: list[Path]) -> None:
        raise PermissionError

    storage._mkdir = fail_mkdir  # type: ignore[method-assign]
    with pytest.raises(ApplicationError) as error:
        initialize_vault(
            vault,
            global_vault_values=(),
            cwd=tmp_path,
            config_template=CONFIG_TEMPLATE,
            storage=storage,
            vault_id_factory=lambda: VAULT_ID,
        )
    assert error.value.code == "VAULT_UNAVAILABLE"
    assert not vault.exists()


def test_init_rejects_traversal_and_conflicting_global_option(tmp_path: Path) -> None:
    storage = FilesystemVaultStorage()
    with pytest.raises(ApplicationError) as unsafe:
        initialize_vault(
            "nested/../vault",
            global_vault_values=(),
            cwd=tmp_path,
            config_template=CONFIG_TEMPLATE,
            storage=storage,
        )
    assert unsafe.value.code == "VAULT_PATH_UNSAFE"

    with pytest.raises(ApplicationError) as conflict:
        initialize_vault(
            "one",
            global_vault_values=("two",),
            cwd=tmp_path,
            config_template=CONFIG_TEMPLATE,
            storage=storage,
        )
    assert conflict.value.code == "VAULT_SELECTION_CONFLICT"


def test_vault_discovery_uses_all_four_levels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FilesystemVaultStorage()
    option_vault = tmp_path / "option"
    env_vault = tmp_path / "environment"
    ancestor_vault = tmp_path / "ancestor"
    default_vault = tmp_path / "default"
    for vault in (option_vault, env_vault, ancestor_vault, default_vault):
        _initialize(vault)
    nested = ancestor_vault / "notes" / "ideas"

    explicit = resolve_vault(
        explicit_values=(str(option_vault),),
        cwd=nested,
        environment={"KNOWLUME_VAULT": str(env_vault)},
        storage=storage,
    )
    assert (explicit.root, explicit.source) == (option_vault, "option")

    environment = resolve_vault(
        explicit_values=(),
        cwd=nested,
        environment={"KNOWLUME_VAULT": str(env_vault)},
        storage=storage,
    )
    assert (environment.root, environment.source) == (env_vault, "environment")

    ancestor = resolve_vault(
        explicit_values=(), cwd=nested, environment={}, storage=storage
    )
    assert (ancestor.root, ancestor.source) == (ancestor_vault, "ancestor")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(storage, "default_vault", lambda: default_vault)
    default = resolve_vault(
        explicit_values=(), cwd=outside, environment={}, storage=storage
    )
    assert (default.root, default.source) == (default_vault, "user-default")


def test_vault_discovery_has_stable_missing_unsupported_and_ambiguous_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = FilesystemVaultStorage()
    missing_default = tmp_path / "missing-default"
    monkeypatch.setattr(storage, "default_vault", lambda: missing_default)
    with pytest.raises(ApplicationError) as required:
        resolve_vault(explicit_values=(), cwd=tmp_path, environment={}, storage=storage)
    assert required.value.code == "VAULT_REQUIRED"

    with pytest.raises(ApplicationError) as missing:
        resolve_vault(
            explicit_values=(str(tmp_path / "absent"),),
            cwd=tmp_path,
            environment={},
            storage=storage,
        )
    assert missing.value.code == "VAULT_NOT_FOUND"

    with pytest.raises(ApplicationError) as ambiguous:
        resolve_vault(
            explicit_values=(str(tmp_path / "one"), str(tmp_path / "two")),
            cwd=tmp_path,
            environment={},
            storage=storage,
        )
    assert ambiguous.value.code == "VAULT_AMBIGUOUS"

    unsupported = tmp_path / "unsupported"
    unsupported.mkdir()
    (unsupported / "knowlume.toml").write_text(
        CONFIG_TEMPLATE.replace("config_version = 1", "config_version = 9"),
        encoding="utf-8",
    )
    with pytest.raises(ApplicationError) as version:
        resolve_vault(
            explicit_values=(str(unsupported),),
            cwd=tmp_path,
            environment={},
            storage=storage,
        )
    assert version.value.code == "VAULT_CONFIG_UNSUPPORTED"


def test_discovery_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    _initialize(actual)
    link = tmp_path / "linked"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this host")
    with pytest.raises(ApplicationError) as error:
        resolve_vault(
            explicit_values=(str(link),),
            cwd=tmp_path,
            environment={},
            storage=FilesystemVaultStorage(),
        )
    assert error.value.code == "VAULT_PATH_UNSAFE"


def test_atomic_write_checks_expected_checksum_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _initialize(vault)
    writer = AtomicFileWriter(vault)
    target = vault / "notes" / "ideas" / "one.md"
    first = writer.write_bytes(target, b"first", expected_checksum=None)
    assert first == sha256_bytes(b"first")
    second = writer.write_bytes(target, b"second", expected_checksum=first)
    assert second == file_checksum(target)
    assert target.read_bytes() == b"second"
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_atomic_write_never_overwrites_a_concurrent_change(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _initialize(vault)
    target = vault / "notes" / "ideas" / "one.md"
    target.write_bytes(b"original")
    expected = file_checksum(target)

    def change_target(state: str, path: Path) -> None:
        assert state == "before_replace"
        path.write_bytes(b"concurrent")

    writer = AtomicFileWriter(vault, fault_hook=change_target)
    with pytest.raises(DomainError) as error:
        writer.write_bytes(target, b"ours", expected_checksum=expected)
    assert error.value.code == "WRITE_CONFLICT"
    assert target.read_bytes() == b"concurrent"


def test_simultaneous_single_file_writers_have_one_winner(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _initialize(vault)
    target = vault / "notes" / "ideas" / "one.md"
    entered = threading.Event()
    release = threading.Event()
    outcomes: list[str] = []

    def hold_before_replace(state: str, path: Path) -> None:
        assert state == "before_replace"
        entered.set()
        assert release.wait(timeout=5)

    def first_writer() -> None:
        try:
            AtomicFileWriter(vault, fault_hook=hold_before_replace).write_bytes(
                target, b"first", expected_checksum=None
            )
            outcomes.append("first-success")
        except DomainError as error:
            outcomes.append(error.code)

    thread = threading.Thread(target=first_writer)
    thread.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(DomainError) as conflict:
            AtomicFileWriter(vault).write_bytes(target, b"second", expected_checksum=None)
        assert conflict.value.code == "WRITE_CONFLICT"
    finally:
        release.set()
        thread.join(timeout=5)
    assert outcomes == ["first-success"]
    assert target.read_bytes() == b"first"


def test_init_cli_help_success_and_typed_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    monkeypatch.setattr("knowlume.cli.read_asset_text", lambda name: CONFIG_TEMPLATE)
    help_result = runner.invoke(app, ["init", "--help"])
    assert help_result.exit_code == 0
    assert "PATH" in help_result.stdout

    vault = tmp_path / "cli-vault"
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code == 0
    assert "Initialized Knowlume vault" in result.stdout
    assert (vault / "knowlume.toml").is_file()

    conflict = runner.invoke(
        app,
        ["--vault", str(tmp_path / "other"), "init", str(vault)],
    )
    assert conflict.exit_code == 3
    assert "VAULT_SELECTION_CONFLICT" in conflict.stderr
    assert str(vault) not in conflict.stderr


def test_init_does_not_modify_git_metadata(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _initialize(vault)
    assert not (vault / ".git").exists()
    assert os.environ.get("GIT_DIR") is None or not (vault / os.environ["GIT_DIR"]).exists()
