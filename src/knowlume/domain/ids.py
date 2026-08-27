from __future__ import annotations

import secrets
import time
from collections.abc import Callable

from knowlume.domain.values import DomainError

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(
    *,
    time_ms: int | None = None,
    random_bytes: Callable[[int], bytes] = secrets.token_bytes,
) -> str:
    timestamp = int(time.time_ns() // 1_000_000) if time_ms is None else time_ms
    if not 0 <= timestamp < 2**48:
        raise DomainError("ID_GENERATION_FAILED", "ULID timestamp is outside the 48-bit range")
    randomness = random_bytes(10)
    if len(randomness) != 10:
        raise DomainError("ID_GENERATION_FAILED", "ULID randomness must contain 10 bytes")
    value = (timestamp << 80) | int.from_bytes(randomness, "big")
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = CROCKFORD[value & 31]
        value >>= 5
    return "".join(encoded)


def new_vault_id() -> str:
    return f"vault_{new_ulid()}"
