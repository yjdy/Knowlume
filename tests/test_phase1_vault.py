from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from knowlume.adapters.filesystem import (
    FilesystemVault,
    checksum_bytes,
    checksum_file,
    load_vault,
    parse_vault_config,
)
from knowlume.cli import app
from knowlume.domain.values import DomainError

ROOT = Path(__file__).resolve().parents[1]
CONFIG_TEXT = (ROOT / "templates/config/v1/knowlume.toml").read_text(encoding="utf-8")
runner = CliRunner()


def _init(path: Path, *, environment: dict[str, str] | None = None) -> FilesystemVault:
    adapter = FilesystemVault(environment=environment or {})
    adapter.initialize(path, CONFIG_TEXT)
    return adapter


def test_initialize_creates_the_portable_vault_topology(tmp_path: Path) -> None:
    target = tmp_path / "Vault with 空格"
    adapter = _init(target)
    vault = load_vault(target)
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
    assert all((vault.root / relative).is_dir() for relative in expected)
    assert (vault.root / "knowlume.toml").read_text(encoding="utf-8") == CONFIG_TEXT
    assert adapter.initialize(target, CONFIG_TEXT) == vault


def test_initialize_supports_long_paths_when_the_platform_does(tmp_path: Path) -> None:
    parent = tmp_path
    try:
        for index in range(6):
            parent = parent / f"long-segment-{index}-abcdefghijklmnopqrstuvwxyz"
            parent.mkdir()
        target = parent / "vault"
        _init(target)
    except OSError:
        pytest.skip("long paths are not enabled on this platform")
    assert load_vault(target).root == target.resolve()


def test_initialize_rejects_nonempty_target_without_partial_output(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(DomainError) as caught:
        FilesystemVault(environment={}).initialize(target, CONFIG_TEXT)
    assert caught.value.code == "VAULT_INVALID"
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not (target / "knowlume.toml").exists()


def test_discovery_precedence_and_nearest_ancestor(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    environment = tmp_path / "environment"
    ancestor = tmp_path / "workspace"
    nearest = ancestor / "nested"
    default = tmp_path / "default"
    for path in (explicit, environment, ancestor, nearest, default):
        _init(path)
    cwd = nearest / "inside" / "deeper"
    cwd.mkdir(parents=True)
    adapter = FilesystemVault(
        environment={"KNOWLUME_VAULT": str(environment)}, default_root=default
    )
    assert adapter.discover(explicit=explicit, cwd=cwd).root == explicit.resolve()
    assert adapter.discover(explicit=None, cwd=cwd).root == environment.resolve()
    ancestor_adapter = FilesystemVault(environment={}, default_root=default)
    assert ancestor_adapter.discover(explicit=None, cwd=cwd).root == nearest.resolve()
    outside = tmp_path / "outside"
    outside.mkdir()
    assert ancestor_adapter.discover(explicit=None, cwd=outside).root == default.resolve()


def test_discovery_and_configuration_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(DomainError) as caught:
        FilesystemVault(environment={}, default_root=tmp_path / "missing").discover(
            explicit=None, cwd=tmp_path
        )
    assert caught.value.code == "VAULT_NOT_FOUND"

    unsupported = CONFIG_TEXT.replace("config_version = 1", "config_version = 2")
    with pytest.raises(DomainError) as caught:
        parse_vault_config(unsupported)
    assert caught.value.code == "VAULT_VERSION_UNSUPPORTED"

    overlapping = CONFIG_TEXT.replace('notes = "notes"', 'notes = "sources/notes"')
    with pytest.raises(DomainError) as caught:
        parse_vault_config(overlapping)
    assert caught.value.code == "VAULT_PATH_CONFLICT"


def test_multiple_environment_vaults_are_ambiguous(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _init(first)
    _init(second)
    adapter = FilesystemVault(
        environment={"KNOWLUME_VAULT": os.pathsep.join((str(first), str(second)))}
    )
    with pytest.raises(DomainError) as caught:
        adapter.discover(explicit=None, cwd=tmp_path)
    assert caught.value.code == "VAULT_AMBIGUOUS"


def test_atomic_write_detects_conflict_and_preserves_newer_content(tmp_path: Path) -> None:
    target = tmp_path / "vault"
    adapter = _init(target)
    vault = load_vault(target)
    relative = "notes/ideas/example.md"
    first = b"first\n"
    first_checksum = adapter.atomic_write(vault, relative, first, None)
    assert first_checksum == checksum_bytes(first)
    path = target / relative
    path.write_bytes(b"newer\n")
    with pytest.raises(DomainError) as caught:
        adapter.atomic_write(vault, relative, b"stale replacement\n", first_checksum)
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    assert path.read_bytes() == b"newer\n"
    assert checksum_file(path) == checksum_bytes(b"newer\n")


def test_atomic_delete_is_checksum_guarded(tmp_path: Path) -> None:
    target = tmp_path / "vault"
    adapter = _init(target)
    vault = load_vault(target)
    relative = "notes/ideas/rollback.md"
    checksum = adapter.atomic_write(vault, relative, b"created\n", None)
    path = target / relative
    path.write_bytes(b"newer\n")
    with pytest.raises(DomainError) as caught:
        adapter.atomic_delete(vault, relative, checksum)
    assert caught.value.code == "VAULT_WRITE_CONFLICT"
    assert path.read_bytes() == b"newer\n"
    adapter.atomic_delete(vault, relative, checksum_bytes(b"newer\n"))
    assert not path.exists()


@pytest.mark.parametrize("relative", ["../outside.md", "/absolute.md", "notes\\bad.md"])
def test_atomic_write_rejects_unsafe_relative_paths(tmp_path: Path, relative: str) -> None:
    target = tmp_path / "vault"
    adapter = _init(target)
    with pytest.raises(DomainError) as caught:
        adapter.atomic_write(load_vault(target), relative, b"unsafe", None)
    assert caught.value.code == "VAULT_PATH_UNSAFE"


def test_symlink_escape_is_rejected_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "vault"
    adapter = _init(target)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = target / "notes" / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are not available for this account")
    with pytest.raises(DomainError) as caught:
        adapter.atomic_write(load_vault(target), "notes/escape/private.md", b"unsafe", None)
    assert caught.value.code == "VAULT_PATH_UNSAFE"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_windows_junction_escape_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "vault"
    adapter = _init(target)
    outside = tmp_path / "outside"
    outside.mkdir()
    junction = target / "notes" / "junction"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.fail(f"could not create Windows junction: {created.stderr}")
    try:
        with pytest.raises(DomainError) as caught:
            adapter.atomic_write(load_vault(target), "notes/junction/private.md", b"unsafe", None)
        assert caught.value.code == "VAULT_PATH_UNSAFE"
    finally:
        junction.rmdir()


def test_init_cli_and_global_vault_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("knowlume.cli.read_asset_text", lambda _: CONFIG_TEXT)
    target = tmp_path / "cli vault"
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code == 0
    assert (target / "knowlume.toml").is_file()

    conflict = runner.invoke(app, ["--vault", str(target), "init", str(tmp_path / "other")])
    assert conflict.exit_code == 2
    assert "VAULT_ARGUMENT_CONFLICT" in conflict.stderr
    assert not (tmp_path / "other").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
def test_read_only_directory_refuses_write(tmp_path: Path) -> None:
    target = tmp_path / "vault"
    adapter = _init(target)
    directory = target / "notes" / "ideas"
    directory.chmod(0o500)
    try:
        with pytest.raises(OSError):
            adapter.atomic_write(load_vault(target), "notes/ideas/blocked.md", b"blocked", None)
    finally:
        directory.chmod(0o700)
