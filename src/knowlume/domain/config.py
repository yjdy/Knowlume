from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, cast

from knowlume.constants import (
    CONFIG_VERSION,
    READABLE_CONFIG_RANGE,
    READABLE_OBJECT_CONTRACT_RANGE,
)
from knowlume.domain.values import DomainError

VAULT_ID_RE = re.compile(r"^vault_[0-9A-HJKMNP-TV-Z]{26}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class VaultPaths:
    sources: PurePosixPath
    notes: PurePosixPath
    snippets: PurePosixPath
    ai_artifacts: PurePosixPath
    relations: PurePosixPath

    def values(self) -> tuple[PurePosixPath, ...]:
        return (self.sources, self.notes, self.snippets, self.ai_artifacts, self.relations)


@dataclass(frozen=True)
class VaultConfig:
    config_version: int
    vault_id: str
    object_contract_version: int
    paths: VaultPaths


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DomainError("VAULT_CONFIG_INVALID", f"{field} must be a mapping")
    return cast(dict[str, Any], value)


def _exact_keys(value: dict[str, Any], expected: set[str], *, field: str) -> None:
    if value.keys() != expected:
        missing = expected - value.keys()
        extra = value.keys() - expected
        details = {"missing": sorted(missing), "extra": sorted(extra)}
        raise DomainError("VAULT_CONFIG_INVALID", f"{field} fields are invalid", details=details)


def _portable_path(value: object, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise DomainError("VAULT_CONFIG_INVALID", f"{field} must be a portable relative path")
    if value.startswith("/") or WINDOWS_ABSOLUTE_RE.match(value):
        raise DomainError("VAULT_CONFIG_INVALID", f"{field} must be relative")
    path = PurePosixPath(value)
    if path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise DomainError("VAULT_CONFIG_INVALID", f"{field} contains traversal or aliases")
    if path.parts[0] == ".knowlume":
        raise DomainError("VAULT_CONFIG_INVALID", f"{field} overlaps reserved machine state")
    return path


def _validate_path_set(paths: VaultPaths) -> None:
    parts = [path.parts for path in paths.values()]
    for index, left in enumerate(parts):
        for right in parts[index + 1 :]:
            common = min(len(left), len(right))
            if left[:common] == right[:common]:
                raise DomainError(
                    "VAULT_CONFIG_INVALID",
                    "configured durable paths must be distinct and non-overlapping",
                )


def parse_vault_config(text: str) -> VaultConfig:
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise DomainError("VAULT_CONFIG_INVALID", "knowlume.toml is not valid TOML") from error
    data = _mapping(value, field="knowlume.toml")
    _exact_keys(
        data,
        {"config_version", "vault_id", "object_contract_version", "paths"},
        field="knowlume.toml",
    )
    config_version = data["config_version"]
    if not isinstance(config_version, int) or isinstance(config_version, bool):
        raise DomainError("VAULT_CONFIG_INVALID", "config_version must be an integer")
    if not READABLE_CONFIG_RANGE[0] <= config_version <= READABLE_CONFIG_RANGE[1]:
        raise DomainError("VAULT_CONFIG_UNSUPPORTED", "configuration version is unsupported")
    object_version = data["object_contract_version"]
    if not isinstance(object_version, int) or isinstance(object_version, bool):
        raise DomainError("VAULT_CONFIG_INVALID", "object_contract_version must be an integer")
    if not READABLE_OBJECT_CONTRACT_RANGE[0] <= object_version <= READABLE_OBJECT_CONTRACT_RANGE[1]:
        raise DomainError("VAULT_CONFIG_UNSUPPORTED", "object Contract version is unsupported")
    vault_id = data["vault_id"]
    if not isinstance(vault_id, str) or VAULT_ID_RE.fullmatch(vault_id) is None:
        raise DomainError("VAULT_CONFIG_INVALID", "vault_id is invalid")
    path_data = _mapping(data["paths"], field="paths")
    _exact_keys(
        path_data,
        {"sources", "notes", "snippets", "ai_artifacts", "relations"},
        field="paths",
    )
    paths = VaultPaths(
        sources=_portable_path(path_data["sources"], field="paths.sources"),
        notes=_portable_path(path_data["notes"], field="paths.notes"),
        snippets=_portable_path(path_data["snippets"], field="paths.snippets"),
        ai_artifacts=_portable_path(path_data["ai_artifacts"], field="paths.ai_artifacts"),
        relations=_portable_path(path_data["relations"], field="paths.relations"),
    )
    _validate_path_set(paths)
    return VaultConfig(
        config_version=config_version,
        vault_id=vault_id,
        object_contract_version=object_version,
        paths=paths,
    )


def render_new_vault_config(template: str, vault_id: str) -> tuple[str, VaultConfig]:
    if VAULT_ID_RE.fullmatch(vault_id) is None:
        raise DomainError("VAULT_CONFIG_INVALID", "generated vault_id is invalid")
    marker = 'vault_id = "vault_01JSTAG7N9Q3V5X8Y2Z4A6B8D2"'
    if template.count(marker) != 1:
        raise DomainError("VAULT_CONFIG_INVALID", "bundled configuration template is invalid")
    rendered = template.replace(marker, f'vault_id = "{vault_id}"')
    config = parse_vault_config(rendered)
    if config.config_version != CONFIG_VERSION:
        raise DomainError("VAULT_CONFIG_UNSUPPORTED", "template configuration version is unsupported")
    return rendered, config
