from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from knowlume.application.errors import ApplicationError
from knowlume.domain.config import VaultConfig, render_new_vault_config
from knowlume.domain.ids import new_vault_id
from knowlume.domain.values import DomainError
from knowlume.ports.vault import VaultStoragePort


@dataclass(frozen=True)
class ResolvedVault:
    root: Path
    config: VaultConfig
    source: str


@dataclass(frozen=True)
class InitResult:
    vault_id: str
    created: bool


def application_error_from_domain(error: DomainError) -> ApplicationError:
    exit_code = {
        "VAULT_PATH_UNSAFE": 6,
        "VAULT_UNAVAILABLE": 5,
        "WRITE_CONFLICT": 4,
    }.get(error.code, 3)
    return ApplicationError(error.code, str(error), exit_code=exit_code)


def _one_explicit_path(
    values: tuple[str, ...], *, cwd: Path, storage: VaultStoragePort
) -> Path | None:
    if not values:
        return None
    normalized = {storage.normalize_path(value, base=cwd) for value in values}
    if len(normalized) != 1:
        raise ApplicationError(
            "VAULT_AMBIGUOUS",
            "global --vault values identify different targets",
            exit_code=3,
        )
    return normalized.pop()


def resolve_vault(
    *,
    explicit_values: tuple[str, ...],
    cwd: Path,
    environment: Mapping[str, str],
    storage: VaultStoragePort,
) -> ResolvedVault:
    try:
        explicit = _one_explicit_path(explicit_values, cwd=cwd, storage=storage)
    except DomainError as error:
        raise application_error_from_domain(error) from error
    if explicit is not None:
        root, source = explicit, "option"
    elif environment.get("KNOWLUME_VAULT"):
        try:
            root = storage.normalize_path(environment["KNOWLUME_VAULT"], base=cwd)
        except DomainError as error:
            raise application_error_from_domain(error) from error
        source = "environment"
    else:
        ancestor = storage.find_nearest_vault(cwd)
        if ancestor is not None:
            root, source = ancestor, "ancestor"
        else:
            default = storage.default_vault()
            if not storage.has_marker(default):
                raise ApplicationError(
                    "VAULT_REQUIRED",
                    "no Knowlume vault could be discovered",
                    exit_code=3,
                )
            root, source = default, "user-default"
    try:
        config = storage.load_config(root)
    except DomainError as error:
        raise application_error_from_domain(error) from error
    return ResolvedVault(root=root, config=config, source=source)


def initialize_vault(
    path: str | Path,
    *,
    global_vault_values: tuple[str, ...],
    cwd: Path,
    config_template: str,
    storage: VaultStoragePort,
    vault_id_factory: Callable[[], str] = new_vault_id,
) -> InitResult:
    try:
        target = storage.normalize_path(path, base=cwd)
        explicit = _one_explicit_path(global_vault_values, cwd=cwd, storage=storage)
    except DomainError as error:
        raise application_error_from_domain(error) from error
    if explicit is not None and explicit != target:
        raise ApplicationError(
            "VAULT_SELECTION_CONFLICT",
            "kb init PATH conflicts with global --vault",
            exit_code=3,
        )
    try:
        rendered, config = render_new_vault_config(config_template, vault_id_factory())
        created = storage.initialize(target, rendered, config)
        if not created:
            existing = storage.load_config(target)
            return InitResult(vault_id=existing.vault_id, created=False)
    except DomainError as error:
        raise application_error_from_domain(error) from error
    return InitResult(vault_id=config.vault_id, created=True)
