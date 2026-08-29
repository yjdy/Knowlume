from __future__ import annotations

import ipaddress
import re

from knowlume.domain.values import DomainError

BUILTIN_REPOSITORY_HOSTS = ("github.com", "gitlab.com")


def normalize_repository_host(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DomainError("VAULT_INVALID", "repository host must be a bare DNS hostname")
    if any(character.isspace() for character in value) or any(
        token in value for token in ("://", "/", "\\", "@", ":", "*")
    ):
        raise DomainError("VAULT_INVALID", "repository host must be a bare DNS hostname")
    candidate = value[:-1] if value.endswith(".") else value
    if not candidate or candidate.endswith(".") or candidate.startswith("["):
        raise DomainError("VAULT_INVALID", "repository host must be a bare DNS hostname")
    try:
        normalized = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise DomainError("VAULT_INVALID", "repository host is not valid IDNA") from error
    if normalized == "localhost" or "." not in normalized:
        raise DomainError("VAULT_INVALID", "repository host must be a public DNS shape")
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        pass
    else:
        raise DomainError("VAULT_INVALID", "repository host cannot be an IP literal")
    labels = normalized.split(".")
    if len(normalized) > 253 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-z0-9-]+", label)
        for label in labels
    ):
        raise DomainError("VAULT_INVALID", "repository host is not a valid DNS hostname")
    return normalized
